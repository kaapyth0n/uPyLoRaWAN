# Project Description

Software for a device called SBI (Smart Boiler Interface) which collects data from sensors, manipulates the output to control the boiler and keeps connection to the LoRaWAN gateway by sending the current values and receiving commands with LoRaWAN.

## LoRaWAN
I'm actually not using TTN infrastructure for my application, I'm using my own gateway which would be connected then to my own server. But anyway, the gateway only supports valid LoRaWAN messages, so I need to register a device in the gateway first. There are two options: OTAA or ABP. For both of them I need to provide the Device EUI, and for OTAA I also need to provide an Application Key, but if I choose ABP I need to provide Device Address, Network Session Key and Application Session Key. Currently we are using ABP mode.

The gateway does not provide the Device Address, Network and Application Session Keys, but rather wants me to put them manually.

The SBI acts as a Class C device, as it's connected to mains.

## Boiler control
We need to manipulate the boiler.
We have to receive the command from the LoRaWAN Gateway so that we have a setpoint for the flow temperature. The format of the command is to be specified.

We will measure the flow temperature with the sensor.

We will have 2 modes of operation of the boiler:
1. Outdoor sensor simulation mode - when the boiler has an outdoor sensor and operates by a certain heating curve, we will disconnect the sensor from the boiler and connect it to the SBI (input 2). After that we will have an additional SSR2-2.10 output module which can take a target NTC10K temperature and simulate the resistance up to 100 kOhm, which would be forwarded as an external temperature sensor to the boiler to make it produce more or less heat.
2. Relay mode - when the boiler does not have an outdoor sensor, we use a relay module to control the boiler directly by turning on and of its burner

## Device components description
The device is a FB2-3_14 board (Fractal Set) with Raspberry Pi Pico W module as a controller and MicroPython installed there.

On this board additionally installed are:

There is IND1-1.1 module installed in the M1 and M2 slots

There is SSR2-2.10 module installed in the M5 slot

There is IO1-2.2 module installed in the M6 slot
There is a 1-Wire sensor connected to the first input of this module.

Also there is a RFM95W LoRa module connected to the following pins of the board:
VIN - +3.3V
GND - GND
DI0 - MOD4_2 - GP14
SCK - MOD3_2 - GP10
MISO - MOD3_3 - GP8
MOSI - MOD3_4 - GP11
CS - MOD3_1 - GP9
RST - MOD4_1 - GP13

On start, the controller loads and runs boot.py file and FrSet.py file is also loaded. FrSet.py is designed to help dealing with the FR modules. Then the controller runs main.py file.
I have also the sample code for dealing with the IND1-1.1 module called IND1_DEMO, it uses a more high-level library called IND1.

There is also a program written in micropython called uPyLoRaWAN (sx127x.py, config.py), which would help us to work with RFM95W module.

## Wi-Fi
There is a Wi-Fi connectivity. In the boot.py if the Wi-Fi is not set up or not connected, the config_portal set up an internal Wi-Fi AP and a very simple WEB interface so the installer could put the appropriate WiFi credentials on site.

## LoRaWAN protocol and Data organisation
Let's plan the protocol for the LoRa communication and project logical structure.
The plan is as follows:
- we split all the useful functionality (API) into meaningful separate parts - "interfaces", such as "controller", "module", 'io1', 'ind1', "wifi", "boiler", etc. Some of the "interfaces" are called "types" because it's the final interface in hierarchy of interfaces for this object.
- all "interfaces" are enumerated like 0, 1, 2, ...
- each "interface" has its own set of "functions", like "controller" would have methods like "getSerialNumber()" and "getModulesList()", "wifi" would have "getWifiSsid()" and "setWifiSsidPassword(ssid, password)", "boiler" would have "setTargetTemperature(setpoint)"...
- all "functions" of an "interface" are enumerated, like 0, 1, 2,..
- each "type" can have multiple instances, called "objects", and each "object" can support many different "interfaces". Usually the set of "interfaces" is defined by "type". Each "object" in a system has its own unique number "id", like 1, 2, 3... usually not exceeding 127. The "0" id is reserved for "broadcast" messages targeting all the objects.
- each object's code is running on some controller and also occupies some kind of a 'slot' inside the controller's memory. Therefore in case there're accidentally two objects with the same id, they can be addressed also with controllerId+slot, mainly for the purpose of changing the id of one of them.
- there is an interface "Object" which support is mandatory for every object in a system. It has "isIdOccupied(id):controllerId,slot,type", "isInterfaceSupported(interface)", "getType()", "getInterfaces()"
- there is an interface called "remoteControl" with a function "getParameter(interface,paramId[,paramIndexN[,paramIndexM]])" and a function "setParameter(interface,paramId[,paramIndexN[,paramIndexM]],paramValue)" to put the convenient way to get access to the object's parameters. Each interface has all their parameters enumerated, sometimes with additional index or two or more. For example, "module" has parameter "sensor" which has an additional sensor index following to get the particular sensor value, same goes for "relay". And also the "object" has parameter "input" and "output" as sometimes you need to connect some sensors or outputs to some inputs or some outputs to "relays". "relay" here is not a real relay, but rather a term to describe a physical output on a module, could be anything like 0-10V or digital output or dry contact.

Now let's define the byte organization of the the communication.
1. All the communication consist of (optional) request and response messages
2. The message consists of the fields: id, interface, function, flags, arguments, return values
3. id, interface, function, paramId, paramIndex, slot and other non-negative fields - these fields are organised in the following order: the most significant bit of a byte indicates that the field value is greater than 127 and the following byte will contain the next more significant 7 bits of the field. Therefore, values 0...127 fit into one byte, values 128...16383 fit into two bytes, and so on.
4. The arguments of a function and return values always have the first byte as indicator of the value byte length, with the most significant bit indicates if the value is signed or unsigned.
5. The list of arguments of a function could be expanded over time when the protocol evolves. Therefore if there are more arguments in the request than expected, the code must ignore the unexpected arguments, but must retain them in the response message.
6. The list of return values could also expand over time and the receiving code should ignore unexpected values.
7. There should be a specific function in "object" class, which would connect the value from another object's particular output to this object's particular input, or read the current state of such connection. In this regard, sensor values are 'outputs' of a module object, and relays are 'inputs' of a module object. An input can only have one source of data (output), but an output can be a source of data for many inputs. 