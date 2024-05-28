#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Raspberry Pi GPIO-control Tango device server and http camera stream.
KITS 2018-05-31.
"""

import re
import socket

import numpy as np
import requests

from raspberry_pi.resource import catch_connection_error

from tango import (AttReqType,
                   AttrWriteType,
                   DispLevel,
                   CmdArgType,
                   Attr,
                   READ_WRITE)
from tango import DevState, DebugIt
from tango.server import Device, attribute, command, pipe, device_property

from .RPi import Raspberry


class RaspberryPiIO(Device):
    Host = device_property(dtype=str)
    Port = device_property(dtype=int, default_value=9788)
    pins = device_property(dtype=(int,))

    def _get_pin(self, attr_name):
        m = re.search('\s*(?P<pin>[\d]+)\s*', attr_name)
        if m:
            pin_number = m.groupdict().get('pin', None)
        else:
            pin_number = None

        if pin_number is None:
            raise Exception('Error geting pin number from  '
                            '[{}]'.format(attr_name))

        return pin_number

    def init_device(self):
        Device.init_device(self)
        self.raspberry = Raspberry(self.Host)

        # No error decorator for the init function
        try:
            self.raspberry.connect_to_pi()
            self.set_state(DevState.ON)
            # Get the list of pins from the device
            available_pins = set(self.raspberry.read_pins_list())

            # Convert self.pins to a set for efficient lookup
            current_pins = set(self.pins)

            # Find pins to remove
            pins_to_remove = ', '.join(map(str, current_pins - available_pins))

            # Remove pins not present in device_pins
            self.pins = list(current_pins & available_pins)

            if pins_to_remove:
                msg = "Removed pins: {}".format(pins_to_remove)
                self.debug_stream(msg)

        except (BrokenPipeError, ConnectionRefusedError,
                ConnectionError, socket.timeout,
                TimeoutError) as connectionerror:
            self.set_state(DevState.FAULT)
            self.debug_stream('Unable to connect to Raspberry Pi TCP/IP'
                              + ' server.')

    def delete_device(self):
        self.raspberry.disconnect_from_pi()
        self.raspberry = None

    def initialize_dynamic_attributes(self):
        for pin_number in self.pins:
            # Create attribute name
            voltage_attrname = "pin{}_voltage".format(pin_number)
            output_attrname = "pin{}_output".format(pin_number)
            # Get tango type
            tango_type = CmdArgType.DevBoolean
            # Create attributes
            voltage_attr = Attr(voltage_attrname,
                                      tango_type, READ_WRITE)
            output_attr = Attr(output_attrname,
                                     tango_type, READ_WRITE)
            # Add attribute and setup read/write/allowed method
            self.add_attribute(
                voltage_attr,
                r_meth=self.read_pin_voltage,
                w_meth=self.write_pin_voltage,
                is_allo_meth=self.is_voltage_allowed)
            self.add_attribute(
                output_attr,
                r_meth=self.read_pin_output,
                w_meth=self.write_pin_output,
                is_allo_meth=self.is_output_allowed)

    @catch_connection_error
    def read_pin_voltage(self, attr):
        attr_name = attr.get_name()
        pin_number = self._get_pin(attr_name)
        value = self.raspberry.readvoltage(pin_number)
        attr.set_value(value)

    @catch_connection_error
    def write_pin_voltage(self, attr):
        w_value = attr.get_write_value()
        attr_name = attr.get_name()
        pin_number = self._get_pin(attr_name)
        output = self.raspberry.readoutput(pin_number)
        if not output or output is None:
            raise ValueError("Pin must be setup as an output first")
        else:
            request = self.raspberry.setvoltage(pin_number, w_value)
            if not request:
                raise ValueError("Pin must be setup as an output first")

    def is_voltage_allowed(self, request):
        if request == AttReqType.READ_REQ:
            return (self.get_state() == DevState.ON)
        if request == AttReqType.WRITE_REQ:
            return (self.get_state() == DevState.ON)

    # Ouptut
    @catch_connection_error
    def read_pin_output(self, attr):
        attr_name = attr.get_name()
        pin_number = self._get_pin(attr_name)
        value = self.raspberry.readoutput(pin_number)
        attr.set_value(value)

    @catch_connection_error
    def write_pin_output(self, attr):
        w_value = attr.get_write_value()
        attr_name = attr.get_name()
        pin_number = self._get_pin(attr_name)
        self.raspberry.setoutput(pin_number, w_value)

    def is_output_allowed(self, request):
        return self.get_state() == DevState.ON

    @command
    def TurnOff(self):
        self.raspberry.turnoff()
        self.set_state(DevState.OFF)

    def is_TurnOff_allowed(self):
        return self.get_state() == DevState.ON

    @command
    def ResetAll(self):
        self.raspberry.resetall()

    def is_ResetAll_allowed(self):
        return self.get_state() == DevState.ON


run = RaspberryPiIO.run_server

if __name__ == "__main__":
    RaspberryPiIO.run_server()
