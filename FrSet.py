import time
import math
from machine import SPI, SoftSPI, Pin, PWM
import uctypes

#буфера для коротких системных сообщений по SPI
tx_irq_2 = bytearray([2,1,0,0,0,0])
rx_irq_2 = bytearray(6)
n_irq = 0    # число прерываний

#---------------------------------------------------------------------------------
#---------------------------------------------------------------------------------
class FrSet:
    def __init__(self, size=8, search=False):
        #версия
        self.version = 'FrSet v0.59'
        
        #v0.59 FrSet(..., search=Falce)
        #v0.58 добавлены типы данных D и (R)
        #v0.57 при отображении текстовых строк непечатаемые символы преобразуются в формат со слешем
        
        #количество модулей - размер основной платы
        self.size = size
        #инициализация линий LED как ШИМ
        self.led_R = PWM(26, 1000, invert=1)
        self.led_G = PWM(27, 1000, invert=1)
        self.led_B = PWM(28, 1000, invert=1)
        self.led(0,5,0)

        # таблица параметров SPI: [номер порта SPI, CS, SCK, MISO, MOSI]
        # вставляем нулевой пустой элемент, так как нумерация модулей идет с 1го
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

        # Создаем списки для объектов SPI и CS (нумерация начинается с 1)
        #self.spi_list = []
        self.spi_cs_list = [None]  # Начинаем с заглушки

        # Инициализируем объекты SPI и CS  для элементов с 1 по 8
        for params in self.spi_table[1:]:
            #инициализируем элемент только если он не пустой
            #spi = SoftSPI(baudrate=1000000, polarity=0, phase=0, sck=params[2], mosi=params[4], miso=params[3])
            #self.spi_list.append(spi)

            spi_cs = Pin(params[1], Pin.OPEN_DRAIN, Pin.PULL_DOWN, value=1)
            self.spi_cs_list.append(spi_cs)
            # configure an irq callback
            #spi_cs.irq(trigger=Pin.IRQ_RISING, handler=self.callback)

        #номер последнего обработанного канала SPI
        self.spi_slot = 0 #несуществующий слот

        #размер буфера данных при обработке пакета
        self.size_buf = 80
        
        #Создаем список для проинициализированных разрешений на прерывание (нумерация начинается с 1)
        # в качестве заглушек укажем Events
        self.en_irq_table = [None, 2, 2, 2, 2, 2, 2, 2, 2]

        #Создаем список обработчиков (нумерация начинается с 1)
        self.en_cb_table = [None, None, None, None, None, None, None, None, None]
        
        #структуры для преобразования int/float tf_data.f32
        self.buf_conv = bytearray(4)
        self.union_f = uctypes.struct(uctypes.addressof(self.buf_conv), {'f32': uctypes.FLOAT32})
        self.union_i = uctypes.struct(uctypes.addressof(self.buf_conv), {'u32': uctypes.UINT32})

        print('*' * 40)
        print(self.version)
        print('*' * 40)
        if search == True :
            self.list_mod()
        
#---------------------------------------------------------------------------------
    #разрешение прерывания от слота slot и параметра модуля номер n
    def spi_en_irq(self, slot, n, handler):
        #занесем номер параметра для этого слота , который инициирует Events
        self.en_irq_table[slot] = n
        #занесем обработчик
        self.en_cb_table[slot] = handler
        #разрешим прерывание по линии CS для этого слота
        self.spi_cs_list[slot].irq(trigger=Pin.IRQ_RISING, handler=handler)
        #разрешим генерацию события в модуле 'n'
        # для этого запишем битовую маску разрешения события в Events_mask модуля
        # битовая маска начинается с праметра 6, сами параметры имеют четные адреса
        self.write(4, 1 << int((n-6)/2), slot=slot)
      
#---------------------------------------------------------------------------------
    #управление светодиодом, 0-100
    def led(self, r, g, b):
        self.led_R.duty_u16(int(65535 / 100 * r))
        self.led_G.duty_u16(int(65535 / 100 * g))
        self.led_B.duty_u16(int(65535 / 100 * b))

#---------------------------------------------------------------------------------
    #выбор конкретного SPI
    def spi_choice(self, n):
        
        #если номер слота 0 или не менялся, то ничего и не делаем
        if self.spi_slot == n or n == 0:
            return
        #начиная со слота №5 на модули идут одни и те же физические линии SPI
        # и разница только в CS
        #будем проводить инициализацию узла SPI
        # только для случаев если , были изменены параметры SPI
        elif (self.spi_slot < 5 and n >= 5) or n < 5:
            try:
                self.spi.deinit()
            except:
                pass
            #spi = SPI(spi_par[n-1][0], 1000000, polarity=0, phase=0, sck=spi_par[n-1][2], mosi=spi_par[n-1][3], miso=spi_par[n-1][4])
            #вынуждено из за ошибки в MicroPython с аппаратным портом(не происходит полная деинициализация и разнве линии оказываются прразитно связаны
            # используем программный SPI(реальная максимальная скорость 500000 ??
            #self.spi = SoftSPI(1000000, polarity=0, phase=0, sck=spi_par[n-1][2], mosi=spi_par[n-1][3], miso=spi_par[n-1][4])

            #каждый раз переинициализируем канал, так как он может быть аппаратным
            self.spi = SoftSPI(baudrate=1000000, polarity=0, phase=0, sck=self.spi_table[n][2], mosi=self.spi_table[n][4], miso=self.spi_table[n][3])
            
        self.spi_slot = n   #сохраним новый номер слота(нумерация слотов с 1)

#---------------------------------------------------------------------------------
    def callback(self, p):
        #определим источник прерывания
        try:
            # Получаем индекс объекта в списке
            slot = self.spi_cs_list.index(p)
            #запрет повторного прерывания
            self.spi_cs_list[slot].irq(handler=None)
            #print(f"Объект найден на позиции {index}")
            print("callback", slot)
        except ValueError:
            print("callback ERROR", p)
            return
        self.led(100, 100, 100) #мигнем светодиодом
        #прочитаем Events в модуле вызвавшем прерывание
        #буфера коротких пакетов
        global tx_6
        global rx_6
        tx_6[0] = self.en_irq_table[slot]  #адрес/номер параметра который был указан при инициализации
        tx_6[1] = 1  #признак чтения
        #посылаем пакет
        self.spi_cs_list[self.spi_slot](0)
        self.spi.write_readinto(tx_6, rx_6)
        self.spi_cs_list[self.spi_slot](1)
        #print(rx_6)
        #восстанавливаем разрешение прерывания
        self.spi_cs_list[self.spi_slot].irq(trigger=Pin.IRQ_RISING, handler=self.callback)
        self.led(0,5,0)         #вернем зеленый цвет
        
        #return rx_6
       
#---------------------------------------------------------------------------------
    #пакет обмена для параметра "parameter", "value" значение параметра,
    # "n" число байт параметра при чтении, "rw" чтение/запись, timeout (мкс)(=0 ->не обрабатывать!),
    # slot номер слота(0-> не менять)
    def packet(self, parameter, value, rw=1, n=4, timeout=200, slot=0):
        
        self.led(100,20,0) #мигнем светодиодом
        
        #проверим, надо ли менять слот
        if slot != 0:
            self.spi_choice(slot)
        
        #подготовка передаваемого пакета
        #- адрес параметра и команда(чтение/запись)
        tx = bytearray([parameter, rw])  #заголовок передаваемого пакета
                                 
        #приведение всех типов с декодированием к bytearray
        if rw == 0:  #это цикл записи
            if isinstance(value, int):     #int
                self.union_i.u32 = value   #int -> bytearray
                tx += self.buf_conv
            elif isinstance(value, float): #float
                self.union_f.f32 = value   #float -> bytearray
                tx += self.buf_conv
            elif isinstance(value, bytearray): #bytearray
                tx += value
            elif isinstance(value, bytes): #bytes
                tx += value
            elif isinstance(value, str):   #str
                tx += bytearray(value.encode())
                tx.append(0x00)
            else:                          #ошибка типа
                return None
        else:        #это цикл чтения
            if isinstance(value, int):     #int
                tx += bytearray(n)
            elif isinstance(value, float): #float
                tx += bytearray(n)
            elif isinstance(value, bytearray): #bytearray
                tx += bytearray(n)
            elif isinstance(value, bytes): #bytes
                tx += bytearray(n)
            elif isinstance(value, str):   #str
                tx += bytearray(n + 1)
            else:                          #ошибка типа
                return None

        rx = bytearray(len(tx)) # создаем приемный буфер одинаковой длинны с передающим
                                # так как у нас дуплексный SPI, сколько отправили - столько же и получили

    #непосредственно дуплексный обмен SPI:
        #проверим, разрешено ли прерывание на этой линии CS
        if self.en_cb_table[self.spi_slot] != None:
            #обмен
            self.spi_cs_list[self.spi_slot](0)
            #запрет прерывания от линии CS
            self.spi_cs_list[self.spi_slot].irq(handler=None)
            
            self.spi.write_readinto(tx, rx)
            self.spi_cs_list[self.spi_slot](1)
            #фактически малая задержка, чтобы CS успел восстановиться
            self.spi_cs_list[self.spi_slot](1)

            #восстанавливаем разрешение прерывания
            self.spi_cs_list[self.spi_slot].irq(trigger=Pin.IRQ_RISING, handler=self.en_cb_table[self.spi_slot])
        else:
            #обмен
            self.spi_cs_list[self.spi_slot](0)
            self.spi.write_readinto(tx, rx)
            self.spi_cs_list[self.spi_slot](1)

        if rx[0] != 0x7E:       #модуль не ответил
            self.led(100,0,0)   #зажжем красный
            return None

        if timeout: #разрешена обработка timeout
            i = 0
            while (rx[1] & 0x01) and (rw == 0):  #это цикл записи  +  бит Busy_slave активен - модуль занят
                time.sleep_us(timeout)
                #проверим, разрешено ли прерывание на этой линии CS
                if self.en_cb_table[self.spi_slot] != None:
                    #обмен
                    self.spi_cs_list[self.spi_slot](0)
                    #запрет прерывания от линии CS
                    self.spi_cs_list[self.spi_slot].irq(handler=None)

                    self.spi.write_readinto(tx, rx)
                    self.spi_cs_list[self.spi_slot](1)
                    #фактически малая задержка, чтобы CS успел восстановиться
                    self.spi_cs_list[self.spi_slot](1)

                    #восстанавливаем разрешение прерывания
                    self.spi_cs_list[self.spi_slot].irq(trigger=Pin.IRQ_RISING, handler=self.en_cb_table[self.spi_slot])
                else:
                    #обмен
                    self.spi_cs_list[self.spi_slot](0)
                    self.spi.write_readinto(tx, rx)
                    self.spi_cs_list[self.spi_slot](1)
                i += 1

#         if rw == 0 and i:
#             print('i =', i, '; n =', len(tx))
#             print(tx)
#             print(rx)

        self.led(0,5,0)         #вернем зеленый цвет LED
    #разбор приемного буфера
        if isinstance(value, int):
            self.buf_conv[0:4] =  rx[2:6]   #преобразование пришедших 4х байт в Int
            return self.union_i.u32
        elif isinstance(value, float):     #преобразование пришедших 4х байт в Float
            self.buf_conv[0:4] =  rx[2:6]
            return self.union_f.f32
        elif isinstance(value, bytearray): #bytearray
            return rx[2:]
        elif isinstance(value, bytes):     #bytes
            return rx[2:]
        elif isinstance(value, str):       #str
                #если это был цикл записи, то вернем пустую строку, иак как может прилететь мусор с управляющими кодами
                #if rw == 0 : return '\x00'
            #на всякий случай ограничиваем маркером \x00 максимально длинный конец
            rx[-1] = 0
        try:
            # Попытка декодировать bytearray в строку
            x = rx[2:]  # Обрезаем первые два байта
            result = []
            for byte in x:
                if 0x20 <= byte <= 0x7E:  # Печатаемые ASCII символы
                    result.append(chr(byte))
                elif byte == 0x00:  # Остановка при байте 0x00
                    break
                else:  # Непечатаемые символы
                    result.append(f"x{byte:02X}")
            return ''.join(result)
        except Exception:
            # Возвращение пустой строки в случае любой ошибки
            return ''
            
        else:                              #ошибка типа
            return None

#---------------------------------------------------------------------------------
    #запись "x" в параметр номер "n" модуля "sl"
    def write(self, parameter, value, slot=0):
        if slot != 0:
            self.spi_choice(slot)
        rw = 0
        self.packet(parameter, value, rw, slot=self.spi_slot)
#---------------------------------------------------------------------------------
    #чтение параметра "parameter" модуля "slot" с автоматическим определением типа и т.д.
    def read(self, parameter, slot=0):
        if slot != 0:
            self.spi_choice(slot)

        if (parameter & 1) == 0: #это чтение самого параметра
            x = self.packet(parameter | 1, '', n=1, slot=self.spi_slot)  #читаем первый символ header
            
            if x == None: #модуль отсутствует
                return None
            
            #узнаем тип переменной из Header самого параметра
            h = x[0]
            if h == 'f' or h == 'F':
                x = self.packet(parameter, 0.0, slot=self.spi_slot)
            elif h == 'b' or h == 'B':
                x = self.packet(parameter, 0, slot=self.spi_slot)
            elif h == 'u' or h == 'U':
                x = self.packet(parameter, 0, slot=self.spi_slot)
            elif h == 's' or h == 'S':
                x = self.packet(parameter, 0, slot=self.spi_slot)
            elif h == 'd' or h == 'D':
                x = self.packet(parameter, 0, slot=self.spi_slot)
            elif h == 'c' or h == 'C':
                x = self.packet(parameter, 0, slot=self.spi_slot)
            elif h == 'h' or h == 'H':
                x = self.packet(parameter, '', n=self.size_buf, slot=self.spi_slot)
                #строка проверена ранее в packet()
                
            else:
                return None #неожиданный формат
            
        else: #это чтение самого Hearder
            x = self.packet(parameter, '', n=self.size_buf, slot=self.spi_slot)
            
            if x == None: #модуль отсутствует
                return None
            
        return x
        
#---------------------------------------------------------------------------------
#---------------------------------------------------------------------------------
#---------------------------------------------------------------------------------
    def binary_to_ascii(self, binary_data):
        result = []
        length = min(128, len(binary_data))  # Ограничение длины строки до 128 байт

        for byte in binary_data[:length]:
            if byte == 0x00:  # Остановка при обнаружении 0x00
                break
            elif 32 <= byte <= 126:  # Печатаемые ASCII символы
                result.append(chr(byte))
            else:  # Непечатаемые символы
                result.append(f"\\x{byte:02x}")

        return ''.join(result)

#---------------------------------------------------------------------------------
#---------------------------------------------------------------------------------
#---------------------------------------------------------------------------------
    #непечатные символы преобразуем в \
    def parse_control_chars(self, input_str):
        result = []
        for char in input_str[:128]:  # Ограничиваемся 128 символами
            byte = ord(char)  # Получаем числовое значение байта
            if 32 <= byte <= 126:  # Печатаемые ASCII символы
                result.append(char)
            else:  # Непечатаемые символы
                result.append(f"\\x{byte:02x}")

        return ''.join(result)
#---------------------------------------------------------------------------------
    #расширенный вывод параметра и полной информации на дисплей
    def read_ex(self, parameter, slot=0):
        if slot != 0:
            self.spi_choice(slot)

        x = self.packet(parameter | 1, ' ', n=self.size_buf, slot=self.spi_slot)  #читаем  header
        
        if x == None: #модуль отсутствует
            return None

        h = x[0]                        #запоминаем тип параметра
        
        #нет смысла проверять строку , это сделано в packet()

        print(x, " --> ", end="")

        if h == 'h' or h == 'H':
            x = self.packet(parameter & 0xFE, ' ', n=self.size_buf, slot=self.spi_slot)  #читаем  parameter
            #print(self.binary_to_ascii(x))
            #print(self.parse_control_chars(x))
            print(x)

        elif h == 'f' or h == 'F':
            x = self.packet(parameter, 0.0, slot=self.spi_slot)
            print("%.3f" % x)
        elif h == 'b' or h == 'B':
            x = self.packet(parameter, 0, slot=self.spi_slot)
            print(bin(x))
        elif h == 'u' or h == 'U':
            x = self.packet(parameter, 0, slot=self.spi_slot)
            print(hex(x))
        elif h == 's' or h == 'S':
            x = self.packet(parameter, 0, slot=self.spi_slot)
            print(hex(x))
        elif h == 'd' or h == 'D':
            x = self.packet(parameter, 0, slot=self.spi_slot)
            print(x)
        elif h == 'c' or h == 'C':
            x = self.packet(parameter, 0, slot=self.spi_slot)
            print(hex(x))
        return h

#---------------------------------------------------------------------------------
    #чтение всех параметров модуля "slot"
    def read_all(self, slot=0):
        if slot != 0:
            self.spi_choice(slot)

        p = self.read(0, slot=self.spi_slot)
        print('*' * 40)
        #print("Module : ", end="")
        print(p)
        p = self.read(1, slot=self.spi_slot)
        print(p)
        print('*' * 40)
        print("Parameters:")
        
        i = 2 #читаем параметры
        while p != 'X' and i <= 254:
            print(i, " ", end="")
            p = self.read_ex(i)
            i += 2

#---------------------------------------------------------------------------------
    #поиск модулей
    def list_mod(self):
        for i in range(1, self.size + 1):
            x = self.read(0, slot=i)
            if x != None:
                # Разделяем строку по символу '/'
                chunks = x.split('/')
                # Убираем пробелы в начале и конце каждого элемента и \x00
                chunks = [chunk.strip().rstrip('\x00') for chunk in chunks]
                print('Slot', i, ' found Module --> ', chunks[1], chunks[2])
        self.led(0, 5, 0)  #мог остаться красный, если последний слот пуст

#---------------------------------------------------------------------------------
    #вывод массива рисунка BMP
    #выводятся строки байт вертикально расположенных
    #выводятся в координаты x y - левый верхний угол
    #в заголовке файла, первые два байта - размер в точках
    #n - номер экрана
    def load_bmp(self, bmp, x, y, n):
        size_x = bmp[0]
        size_y = bmp[1]
        #задать начальный угол
        self.write(6, bytes([x, y, 0, 1 + n * 16]))         #экран n,режим SET; поставить курсор X=x, Y=y
        self.write(6, bytes([x + size_x - 1, y + size_y - 1, 0xFE, 1 + n * 16]))  #экран n,режим SET;вывод графики,поставить курсор X=, Y=
        i = 0
        while i <= (size_y / 8) :
            self.write(8, bmp[2 + i * size_x : 2 + i * size_x + size_x])
            i += 1
    
#---------------------------------------------------------------------------------
#---------------------------------------------------------------------------------

def cb_1(p):
    global n_irq
    n_irq += 1
    #запрет повторного прерывания
#    fr.spi_cs_list[2].irq(handler=None)
    #print('pin change2', p)
    #time.sleep_us(10000)
    
    #fr.led(100, 100, 100) #мигнем светодиодом
    #прочитаем Events в модуле вызвавшем прерывание
    #буфера коротких пакетов
#    global tx_irq_2
#    global rx_irq_2
    #tx_6[0] = fr.en_irq_table[2]  #адрес/номер параметра который был указан при инициализации
    #tx_6[1] = 1  #признак чтения
    #посылаем пакет
#    fr.spi_cs_list[2](0)
#    fr.spi.write_readinto(tx_irq_2, rx_irq_2)
#    fr.spi_cs_list[2](1)
#    fr.spi_cs_list[2](1)
#    print(rx_irq_2)
    #восстанавливаем разрешение прерывания
#    fr.spi_cs_list[2].irq(trigger=Pin.IRQ_RISING, handler=fr.en_cb_table[2])
    #fr.led(0,5,0)         #вернем зеленый цвет
    


#fr=FrSet()
#fr.spi_choice(2)
#fr.spi_en_irq(2, 28, cb_1)
