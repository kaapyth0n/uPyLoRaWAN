import time
import math
from machine import SPI, SoftSPI, Pin, PWM
import uctypes

# --------------------------------------------------------------------------------------
# FrSet v0.64
# --------------------------------------------------------------------------------------
# v0.64 18-02-2026 — улучшения:
#   read_all(): чистый вывод — выровненные номера, разделители, итог, без строки 'X'
#   read_ex(): разделитель " = " вместо " --> "
#   wait_event(timeout_s): ожидание IRQ из FIFO с таймаутом
#   read_notify(slot): чтение уведомления от Slave (Number, Function, Addr_Reg, Modbus_Buf)
#
# v0.63 18-02-2026 — исправления:
#   FIX: IRQ_FALLING -> IRQ_RISING (исключает pending edge от SPI-транзакции)
#   FIX: had_irq в packet() проверяет irq_active[] вместо en_cb_table[]
#        (теперь FIFO-режим тоже защищён от ложных IRQ при SPI-обмене)
#   FIX: удалён модульный код (fr=FrSet(), while True:) — блокировал import
#   FIX: удалён пример обработчика с SPI/print внутри ISR
#   Добавлена LED-индикация SPI-обмена (оранжевый, как в v0.61)
# --------------------------------------------------------------------------------------
#v0.62 — первая версия с FIFO событий
#v0.61 при обработке знаковых целых добавлены отрицательные значения
#v0.60 добавлен тип данныхR
#v0.59 FrSet(..., search=Falce)
#v0.58 добавлены типы данных D и (R)
#v0.57 при отображении текстовых строк непечатаемые символы преобразуются в формат со слешем
# --------------------------------------------------------------------------------------


class FrSet:
    def __init__(self, size=8, search=False, max_fifo_len=128):
        """Главный класс работы с наборными модулями FrSet на материнской плате.

        :param size:        количество посадочных мест (слотов) на материнке
        :param search:      если True — при старте вызвать list_mod() (медленнее старта)
        :param max_fifo_len:ограничение длины FIFO событий (защита от переполнения)
        """
        # Версия
        self.version = 'FrSet v0.64'

        # Константы/параметры
        self.size = size                   # число слотов
        self.size_buf = 80                 # буфер при чтении строк/RAW
        self.max_fifo_len = max_fifo_len   # ограничение длины очереди событий

        # Светодиоды индикации состояния (ШИМ). Значения PWM/параметры — как в v0.61
        self.led_R = PWM(26, 1000, invert=1)
        self.led_G = PWM(27, 1000, invert=1)
        self.led_B = PWM(28, 1000, invert=1)
        self.led(0, 5, 0)

        # Таблица линий SPI и CS (индексация слотов с 1 — первый элемент пустышка)
        # Формат: [spi_num, CS, SCK, MISO, MOSI]
        self.spi_table = [
            [None],
            [0, 1, 2, 0, 3],
            [0, 5, 6, 4, 7],
            [1, 9, 10, 8, 11],
            [1, 13, 14, 12, 15],
            [0, 17, 18, 16, 19],
            [0, 20, 18, 16, 19],
            [0, 21, 18, 16, 19],
            [0, 22, 18, 16, 19]
        ]

        # Список объектов CS-пинов (индексация с 1; 0 — заглушка)
        self.spi_cs_list = [None]
        for params in self.spi_table[1:]:
            # Открытый коллектор + подтяжка вниз + стартовое значение 1 (неактивный CS)
            cs_pin = Pin(params[1], Pin.OPEN_DRAIN, Pin.PULL_DOWN, value=1)
            self.spi_cs_list.append(cs_pin)

        # Текущий выбранный слот (0 = ещё не выбран)
        self.spi_slot = 0

        # Очередь событий (FIFO) и счётчик переполнений
        # Событие — кортеж (slot, timestamp_us)
        self.irq_fifo = []
        self.irq_overflow = 0

        # Флаг: зарегистрирован ли IRQ на пине данного слота (индексы 0..size)
        # Используется в packet() для защиты SPI от ложных IRQ
        self.irq_active = [False] * (self.size + 1)

        # Таблица зарегистрированных «жёстких» обработчиков (индексы 1..size)
        # Если None — события слота идут в FIFO
        self.en_cb_table = [None] * (self.size + 1)

        # Таблица «какой параметр генерирует Events» для каждого слота (опционально)
        # Можно использовать при настройке маски событий на модуле, если нужно.
        self.en_irq_table = [None] * (self.size + 1)

        # Буфер и uctypes-"союзы" для конвертаций float32 <-> bytes и u32 <-> bytes
        self.buf_conv = bytearray(4)
        self.union_f = uctypes.struct(uctypes.addressof(self.buf_conv), {'f32': uctypes.FLOAT32})
        self.union_i = uctypes.struct(uctypes.addressof(self.buf_conv), {'u32': uctypes.UINT32})

        print('*' * 40)
        print(self.version)
        print('*' * 40)
        if search:
            self.list_mod()

    # ----------------------------------------------------------------------------------
    # Утилита: управление RGB LED в процентах (0..100)
    def led(self, r, g, b):
        self.led_R.duty_u16(int(65535 / 100 * r))
        self.led_G.duty_u16(int(65535 / 100 * g))
        self.led_B.duty_u16(int(65535 / 100 * b))

    # ----------------------------------------------------------------------------------
    # Выбор аппаратного/программного SPI для слота n (переконфигурация по необходимости)
    def spi_choice(self, n):
        # Если номер слота не меняется — ничего не делаем
        if self.spi_slot == n or n == 0:
            return

        #начиная со слота №5 на модули идут одни и те же физические линии SPI
        # и разница только в CS
        #будем проводить инициализацию узла SPI
        # только для случаев если , были изменены параметры SPI

        # При смене диапазона ( <5 → >=5 или наоборот ) требуется переинициализация
        if (self.spi_slot < 5 and n >= 5) or n < 5:
            try:
                self.spi.deinit()
            except Exception:
                pass

            #каждый раз переинициализируем канал, так как он может быть аппаратным

            # Используем программный SPI (SoftSPI) — как в v0.61
            self.spi = SoftSPI(
                baudrate=1000000, polarity=0, phase=0,
                sck=self.spi_table[n][2], mosi=self.spi_table[n][4], miso=self.spi_table[n][3]
            )

        # Запоминаем текущий активный слот
        self.spi_slot = n

    # ----------------------------------------------------------------------------------
    # ВНУТРЕННИЙ: универсальный IRQ-коллбэк. Максимально короткий.
    # Ничего тяжёлого внутри (никаких SPI-операций, print, аллокаций!).
    def _irq_callback(self, pin):
        try:
            slot = self.spi_cs_list.index(pin)  # определить, кто дёрнул CS
        except ValueError:
            return  # неизвестный пин — игнор

        # Если у слота назначен «жёсткий» обработчик — вызываем его прямо отсюда
        # ВАЖНО: обработчик должен быть легковесным (флаг, инкремент счётчика)!
        # Никаких SPI-операций, print(), аллокаций памяти!
        handler = self.en_cb_table[slot]
        if handler is not None:
            try:
                handler(slot)
            except Exception:
                pass
            return

        # Иначе отправляем событие в FIFO (номер слота + метка времени)
        if len(self.irq_fifo) < self.max_fifo_len:
            self.irq_fifo.append((slot, time.ticks_us()))
        else:
            # Фиксируем переполнение очереди
            self.irq_overflow += 1

    # ----------------------------------------------------------------------------------
    # Публичное API: разрешить IRQ на слоте и (опционально) назначить «жёсткий» обработчик
    def spi_en_irq(self, slot, handler=None, event_param=None):
        """Разрешить прерывания для слота.

        :param slot: номер слота (1..size)
        :param handler: функция-обработчик или None (если None — события пойдут в FIFO)
                        Сигнатура: handler(slot). ТОЛЬКО легковесные операции!
        :param event_param: опционально — номер параметра (>=6, чётный),
                             для которого включить бит Events_mask на модуле.
                             Формула: Events_mask |= 1 << ((event_param - 6) / 2)
        """
        # Запоминаем обработчик и/или параметр событий
        self.en_cb_table[slot] = handler
        self.en_irq_table[slot] = event_param
        self.irq_active[slot] = True

        # Подписываемся на IRQ по фронту (RISING) — после завершения импульса модуля.
        # RISING безопаснее FALLING: исключает pending edge от SPI-транзакции
        # при восстановлении обработчика в packet().
        self.spi_cs_list[slot].irq(trigger=Pin.IRQ_RISING, handler=self._irq_callback)

        # включить маску Events на модуле
        # Универсальная конвенция Fr-Set: bit = (param_num - 6) / 2
        if event_param is not None:
            self.write(4, 1 << int((event_param - 6) / 2), slot=slot)

    # ----------------------------------------------------------------------------------
    # Публичное API: снять IRQ со слота и отключить его обработчик
    def spi_dis_irq(self, slot):
        self.en_cb_table[slot] = None
        self.en_irq_table[slot] = None
        self.irq_active[slot] = False
        try:
            self.spi_cs_list[slot].irq(handler=None)
        except Exception:
            pass

    # ----------------------------------------------------------------------------------
    # Публичное API: забрать одно событие из FIFO (возвращает (slot, ticks_us) или None)
    def get_event(self):
        if self.irq_fifo:
            return self.irq_fifo.pop(0)
        return None

    # Быстро очистить очередь событий
    def clear_events(self):
        self.irq_fifo.clear()
        self.irq_overflow = 0

    # ----------------------------------------------------------------------------------
    # Публичное API: ожидание IRQ из FIFO с таймаутом
    def wait_event(self, timeout_s=3.0):
        """Ожидание события из FIFO с таймаутом.

        :param timeout_s: максимальное время ожидания в секундах (default 3.0)
        :return: (slot, ticks_us) или None при таймауте
        """
        t0 = time.ticks_ms()
        while True:
            ev = self.get_event()
            if ev is not None:
                return ev
            if time.ticks_diff(time.ticks_ms(), t0) > timeout_s * 1000:
                return None
            time.sleep(0.01)

    # ----------------------------------------------------------------------------------
    # Публичное API: чтение уведомления от Slave-модуля
    def read_notify(self, slot, p_num=12, p_func=10, p_addr=8, p_buf=14):
        """Чтение уведомления от Slave (Number, Function, Addr_Reg, Modbus_Buf).

        Порядок чтения важен: Number первым (сбрасывается при чтении).
        Параметры по умолчанию = IRC1-1 / LIN1-1.

        :param slot: номер слота модуля
        :param p_num: номер параметра Number (default 12)
        :param p_func: номер параметра Function (default 10)
        :param p_addr: номер параметра Addr_Reg (default 8)
        :param p_buf: номер параметра Modbus_Buf (default 14)
        :return: (number, function, addr_reg, data) или None если idle (Number==1000)
        """
        n = self.read(p_num, slot=slot)
        if n is None or n == 1000:
            return None
        func = self.read(p_func, slot=slot)
        addr = self.read(p_addr, slot=slot)
        data = self.read(p_buf, slot=slot)
        return (n, func, addr, data)

    # ----------------------------------------------------------------------------------
    # Полезная утилита: преобразование u32 из модуля в знаковый int32
    def to_signed32(self, val):
        if val & 0x80000000:
            return val - 0x100000000
        return val

    # ----------------------------------------------------------------------------------
    # НИЗКОУРОВНЕВЫЙ обмен по SPI (одна транзакция):
    # - формирует «tx» по типу value и режиму rw (0=write, 1=read)
    #     "n" число байт параметра при чтении, timeout (мкс)(=0 ->не обрабатывать!)
    # - делает duplex-транзакцию write_readinto(tx, rx)
    # - ВАЖНО: на время транзакции IRQ на текущем CS временно отключаются (если были включены)
    # - возвращает распакованное значение нужного типа (или None при ошибке ответа)
    def packet(self, parameter, value, rw=1, n=4, timeout=200, slot=0):

        self.led(100, 20, 0)  #мигнем оранжевым — SPI-обмен

        # Возможность сменить слот «на лету» в вызове
        if slot != 0:
            self.spi_choice(slot)

        # Заголовок кадра: [адрес параметра, команда (0=write, 1=read)]
        tx = bytearray([parameter, rw])

        #приведение всех типов с декодированием к bytearray
        # Подготовка полезной нагрузки в зависимости от типа value
        if rw == 0:  # запись
            if isinstance(value, int):         #int
                self.union_i.u32 = value       #int -> bytearray
                tx += self.buf_conv
            elif isinstance(value, float):     #float
                self.union_f.f32 = value       #float -> bytearray
                tx += self.buf_conv
            elif isinstance(value, (bytearray, bytes)): #bytearray #bytes
                tx += value
            elif isinstance(value, str):       #str
                tx += bytearray(value.encode())
                tx.append(0x00)                # C-строка (для модулей это удобно)
            else:                              #ошибка типа
                return None
        else:  # чтение
            # Выделяем приёмный размер: для строк +1 байт на терминатор
            rx_len = n if not isinstance(value, str) else (n + 1)
            tx += bytearray(rx_len)

        # Приёмный буфер той же длины (SPI дуплексный: сколько отправили — столько приняли)
        rx = bytearray(len(tx))

        # --- ЗАЩИТА ОТ ЛОЖНЫХ IRQ во время SPI: временно отключаем IRQ на текущем CS
        # irq_active[] — истинный признак наличия IRQ (работает и для FIFO, и для handler)
        has_irq = self.irq_active[self.spi_slot]
        if has_irq:
            try:
                self.spi_cs_list[self.spi_slot].irq(handler=None)
            except Exception:
                pass

        # Обмен (внешний протокол — поднять/опустить CS вокруг транзакции)
        self.spi_cs_list[self.spi_slot](0)
        self.spi.write_readinto(tx, rx)
        self.spi_cs_list[self.spi_slot](1)
        # Небольшая пауза, чтобы CS точно вернулся в пассив (микросекунды)
        self.spi_cs_list[self.spi_slot](1)

        # Восстанавливаем IRQ, если было включено
        if has_irq:
            try:
                self.spi_cs_list[self.spi_slot].irq(trigger=Pin.IRQ_RISING, handler=self._irq_callback)
            except Exception:
                pass

        # Проверка «сигнатуры ответа» модуля (как и в v0.61): 0x7E = "ответ валиден"
        if rx[0] != 0x7E:
            # Красная индикация ошибки
            self.led(100, 0, 0)
            return None

        # Обработка busy в режиме записи (если модуль занят)
        if timeout:
            i = 0
            while (rx[1] & 0x01) and (rw == 0):  # бит Busy_slave активен + мы в режиме записи
                time.sleep_us(timeout)
                # Повторяем транзакцию (с той же защитой от IRQ)
                if has_irq:
                    try:
                        self.spi_cs_list[self.spi_slot].irq(handler=None)
                    except Exception:
                        pass
                self.spi_cs_list[self.spi_slot](0)
                self.spi.write_readinto(tx, rx)
                self.spi_cs_list[self.spi_slot](1)
                self.spi_cs_list[self.spi_slot](1)
                if has_irq:
                    try:
                        self.spi_cs_list[self.spi_slot].irq(trigger=Pin.IRQ_RISING, handler=self._irq_callback)
                    except Exception:
                        pass
                i += 1

        # Зелёная индикация «успешно»
        self.led(0, 5, 0)

        # Разбор приёмного буфера в нужный тип
        if isinstance(value, int):
            self.buf_conv[0:4] = rx[2:6]   #преобразование пришедших 4х байт в Int
            return self.union_i.u32
        elif isinstance(value, float):     #преобразование пришедших 4х байт в Float
            self.buf_conv[0:4] = rx[2:6]
            return self.union_f.f32
        elif isinstance(value, (bytearray, bytes)): #bytearray #bytes
            return rx[2:]
        elif isinstance(value, str):       #str
            # Обрезаем до нуля и фильтруем непечатаемые символы в xNN
            rx[-1] = 0
            x = rx[2:]
            out = []
            for b in x:
                if b == 0x00:
                    break
                if 0x20 <= b <= 0x7E:
                    out.append(chr(b))
                else:
                    out.append(f"x{b:02X}")
            return ''.join(out)
        else:
            return None

    # ----------------------------------------------------------------------------------
    # Запись значения в параметр модуля
    def write(self, parameter, value, slot=0):
        if slot != 0:
            self.spi_choice(slot)
        self.packet(parameter, value, rw=0, slot=self.spi_slot)

    # ----------------------------------------------------------------------------------
    # Чтение параметра модуля с автоопределением типа по header
    def read(self, parameter, slot=0):
        if slot != 0:
            self.spi_choice(slot)

        if (parameter & 1) == 0:  # чтение САМОГО параметра (не заголовка)
            # сначала читаем первый символ header, чтобы понять тип
            x = self.packet(parameter | 1, '', n=1, slot=self.spi_slot)
            if x is None:
                return None
            h = x[0]

            if h in ('f', 'F'):
                x = self.packet(parameter, 0.0, slot=self.spi_slot)
            elif h in ('b', 'B'):
                x = self.packet(parameter, 0, slot=self.spi_slot)
            elif h in ('u', 'U'):
                x = self.packet(parameter, 0, slot=self.spi_slot)
            elif h in ('s', 'S'):
                x = self.packet(parameter, 0, slot=self.spi_slot)
                x = self.to_signed32(x)
            elif h in ('d', 'D'):
                x = self.packet(parameter, 0, slot=self.spi_slot)
                x = self.to_signed32(x)
            elif h in ('c', 'C'):
                x = self.packet(parameter, 0, slot=self.spi_slot)
            elif h in ('h', 'H'):
                x = self.packet(parameter, '', n=self.size_buf, slot=self.spi_slot)
            elif h in ('r', 'R'):
                x = self.packet(parameter, b'', n=self.size_buf, slot=self.spi_slot)
            else:
                return None
        else:
            # чтение HEADER напрямую
            x = self.packet(parameter, '', n=self.size_buf, slot=self.spi_slot)
            if x is None:
                return None
        return x

    # ----------------------------------------------------------------------------------
    # Расширенный вывод параметра (печать на консоль)
    def read_ex(self, parameter, slot=0):
        if slot != 0:
            self.spi_choice(slot)

        x = self.packet(parameter | 1, ' ', n=self.size_buf, slot=self.spi_slot)  # читаем header
        if x is None:
            return None
        h = x[0]

        print(x, " = ", end="")
        if h in ('h', 'H'):
            x = self.packet(parameter & 0xFE, ' ', n=self.size_buf, slot=self.spi_slot)
            print(x)
        elif h in ('r', 'R'):
            x = self.packet(parameter & 0xFE, b'\x00', n=self.size_buf, slot=self.spi_slot)
            print(' '.join(f'{byte:02X}' for byte in x))
        elif h in ('f', 'F'):
            x = self.packet(parameter, 0.0, slot=self.spi_slot)
            print("%.3f" % x)
        elif h in ('b', 'B'):
            x = self.packet(parameter, 0, slot=self.spi_slot)
            print(bin(x))
        elif h in ('u', 'U'):
            x = self.packet(parameter, 0, slot=self.spi_slot)
            print(hex(x))
        elif h in ('s', 'S'):
            x = self.packet(parameter, 0, slot=self.spi_slot)
            x = self.to_signed32(x)
            print(hex(x))
        elif h in ('d', 'D'):
            x = self.packet(parameter, 0, slot=self.spi_slot)
            x = self.to_signed32(x)
            print(x)
        elif h in ('c', 'C'):
            x = self.packet(parameter, 0, slot=self.spi_slot)
            print(hex(x))
        return h

    # ----------------------------------------------------------------------------------
    # Чтение всех параметров слота
    # v0.64: чистый вывод — выровненные номера, разделители, итог, без строки 'X'
    def read_all(self, slot=0):
        if slot != 0:
            self.spi_choice(slot)

        # Читаем Module_type (param 0)
        p = self.read(0, slot=self.spi_slot)
        print('=' * 48)
        print(p)
        print('=' * 48)

        count = 0
        i = 2
        while i <= 254:
            # Peek header (1 байт) — проверка на 'X' (конец списка) без печати
            hdr = self.packet(i | 1, '', n=1, slot=self.spi_slot)
            if hdr is None or (len(hdr) > 0 and hdr[0] == 'X'):
                break
            # Выровненный номер параметра (3 символа, правое выравнивание)
            print('%3d  ' % i, end="")
            self.read_ex(i)
            count += 1
            i += 2

        print('=' * 48)
        print('%d parameters' % count)

    # ----------------------------------------------------------------------------------
    # Поиск модулей по слотам
    def list_mod(self):
        for i in range(1, self.size + 1):
            x = self.read(0, slot=i)
            if x is not None:
                chunks = x.split('/')
                chunks = [chunk.strip().rstrip('\x00') for chunk in chunks]
                # Защитимся от коротких строк header
                if len(chunks) >= 3:
                    print('Slot', i, ' found Module --> ', chunks[1], chunks[2])
                else:
                    print('Slot', i, ' found Module --> ', x)
        self.led(0, 5, 0)

    # ----------------------------------------------------------------------------------
    # Вывод BMP-массива в модуль-экран (IND1)
    # В заголовке BMP первые 2 байта — размер (в точках). Далее байты вертикальных колонок.
    def load_bmp(self, bmp, x, y, n):
        size_x = bmp[0]
        size_y = bmp[1]
        # Установить окно вывода
        self.write(6, bytes([x, y, 0, 1 + n * 16]))
        self.write(6, bytes([x + size_x - 1, y + size_y - 1, 0xFE, 1 + n * 16]))
        i = 0
        while i <= (size_y / 8):
            self.write(8, bmp[2 + i * size_x: 2 + i * size_x + size_x])
            i += 1
