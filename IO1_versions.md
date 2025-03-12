# Versions of the IO1 modules

## Initial version 0.87

Initially there was the module which had the following description:

```
>>> fr.read_all(6)
****************************************
FrSet / IO1-2.2 / v0.87 / p3.22
H 2*In_PT1000/1Wire/PWMin/Logic; 1*Out_DAC/PWM
****************************************
Parameters:
2  b Events  --> 0b0
4  b Events_mask  --> 0b0
6  F T_L1; C  --> nan
8  f T_min_L1; C  --> nan
10  f T_max_L1; C  --> nan
12  F T_L2; C  --> nan
14  f T_min_L2; C  --> nan
16  f T_max_L2; C  --> nan
18  F T_CPU; C  --> 29.774
20  F V_CPU; V  --> 3.301
22  F V_24; V  --> 4.817
24  F V_L3; V  --> 0.035
26  c PID_CR; 1:IN_par; 0:OUT_par  --> 0x624
28  f PID_set  --> 40.000
30  f PID_kP  --> 1.000
32  f PID_kI  --> 0.100
34  f PID_kD  --> 0.010
36  f DAC_L3; 0.0/22.5; V  --> nan
38  f PWM_L3; 0.0/100.0; %  --> 0.000
40  B D_IN_L1; 0,1  --> 0b1
42  B D_IN_L2; 0,1  --> 0b1
44  c LEDs; 3:R 0/100; 2:G 0/100; 1:B 0/100; 0:N 0/7,15  --> 0xf0
46  h ID_1wire_L1  --> 288AE1060E0000D1
48  h ID_1wire_L2  --> 
50  U FRQ_in_L1; Hz  --> 0x0
52  F PWM_in_L1; %  --> 100.000
54  X  --> 
```

The PID regulation on this version was broken, and most importantly, once enabled, it was impossible to disable it without power cycle.

No systems with this module versions actually used the analog output of it

## Second version 0.89

This version was deployed on one of the systems which required the analog output regulation.

>>>
Вкратце:
-Вставил на 36 и 38й параметры
Минимальное и максимальное ограничение ПИД. Остальные параметры сдвинулись вверх.
-деинсталяцию ПИД-надо записать в конфигурацию 0.
>>>

```
>>> fr.read_all(6)
****************************************
FrSet / IO1-2.22 / v0.89 / p3.22
H 2*In_PT1000/1Wire/PWMin/Logic; 1*Out_DAC/PWM
****************************************
Parameters:
2  b Events  --> 0b0
4  b Events_mask  --> 0b0
6  F T_L1; C  --> nan
8  f T_min_L1; C  --> 0.000
10  f T_max_L1; C  --> 0.000
12  F T_L2; C  --> nan
14  f T_min_L2; C  --> 0.000
16  f T_max_L2; C  --> 0.000
18  F T_CPU; C  --> 24.498
20  F V_CPU; V  --> 3.324
22  F V_24; V  --> 4.731
24  F V_L3; V  --> 0.036
26  c PID_CR; 1:IN_par; 0:OUT_par  --> 0x0
28  f PID_set  --> 0.000
30  f PID_kP  --> 1.000
32  f PID_kI  --> 0.100
34  f PID_kD  --> 0.010
36  f PID_min  --> 0.000
38  f PID_max  --> 10.000
40  f DAC_L3; 0.0/22.5; V  --> 0.000
42  f PWM_L3; 0.0/100.0; %  --> 0.000
44  B D_IN_L1; 0,1  --> 0b1
46  B D_IN_L2; 0,1  --> 0b1
48  c LEDs; 3:R 0/100; 2:G 0/100; 1:B 0/100; 0:N 0/7,15  --> 0xf0
50  h ID_1wire_L1  --> 
52  h ID_1wire_L2  --> 
54  U FRQ_in_L1; Hz  --> 0x0
56  F PWM_in_L1; %  --> 100.000
58  X  -->
```

This version is generally fine, but the PID regulation was not really nice, it was too jerky, so we had to rework that.

Use only the software PID regulation with this module!

## Third version 0.90

This module will be installed on newer installations, but it has the address numbers changed again.

```
>>> fr.read_all(6)
****************************************
FrSet / IO1-2.22 / v0.90 / p3.22
H 2*In_PT1000/1Wire/PWMin/Logic; 1*Out_DAC/PWM
****************************************
Parameters:
2  b Events  --> 0b0
4  b Events_mask  --> 0b0
6  F T_L1; C  --> nan
8  f T_min_L1; C  --> 0.000
10  f T_max_L1; C  --> 0.000
12  F T_L2; C  --> nan
14  f T_min_L2; C  --> 0.000
16  f T_max_L2; C  --> 0.000
18  F T_CPU; C  --> 27.855
20  F V_CPU; V  --> 3.304
22  F V_24; V  --> 5.214
24  F V_L3; V  --> 0.000
26  c PID_CR; 1:IN_par; 0:OUT_par  --> 0x0
28  f PID_set  --> 0.000
30  f PID_kP  --> 1.000
32  f PID_Ti  --> 1.000
34  f PID_Td  --> 0.000
36  f PID_min  --> 0.000
38  f PID_max  --> 10.000
40  f PID_i_min  --> -50.000
42  f PID_i_max  --> 50.000
44  f DAC_L3; 0.0/22.5; V  --> 0.000
46  f PWM_L3; 0.0/100.0; %  --> 0.000
48  B D_IN_L1; 0,1  --> 0b1
50  B D_IN_L2; 0,1  --> 0b1
52  c LEDs; 3:R 0/100; 2:G 0/100; 1:B 0/100; 0:N 0/7,15  --> 0xf0
54  h ID_1wire_L1  --> 
56  h ID_1wire_L2  --> 
58  U FRQ_in_L1; Hz  --> 0x0
60  F PWM_in_L1; %  --> 100.000
62  X  -->
```

The comments from the producer on this issue are as follows:
>>>
Теперь вопросы:
- есть ли какой-то удобный способ узнать версию ПО на модуле? Кроме как парсить вывод fr.read_all?
- есть ли какой-то удобный способ записывать значения не по номеру адреса, а по литеральной строке типа "DAC_L3", чтобы не зависеть от версий прошивки?

версии модуля, протокола и прошивки это параметры 0 и 1.
адрес можно добыть из хедера параметра, адрес с версией могут быть изменены, а имя остается.
>>>

So we can take it into account while implementing future code.