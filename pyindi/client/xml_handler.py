#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File      :   pyindi/client/xml_handler.py
@Time      :   2023/03
@Author    :   Stefano Sartor
@Version   :   0.1
@Contact   :   sartor@oavda.it
@License   :   MIT
@Copyright :   (C) 2023 FONDAZIONE CLÉMENT FILLIETROZ-ONLUS
'''


from xml.sax import ContentHandler
from xml.etree import ElementTree as etree
import logging
import io

class XMLHandler(ContentHandler):

    def __init__(self):
        self._watched = {}
        self._is_child = False
        self._currentElement = None
        self._rootElement = None
        self._currentMessage = None

        self.def_property = lambda x: x
        self.set_property = lambda x: x
        self.del_property = lambda x: x
        self.new_message = lambda x: x

        super().__init__()

    def startElement(self, name, attr):
        try:
            if name == "root":
                return

            if name[:3] not in ("set", "def","new", "one", "mes", "del"):
                return

            if self._rootElement is not None:
                newElement = etree.Element(name, **dict(attr))
                self._currentElement.append(newElement)
                self._currentElement = newElement
                return

            if name[:3] in ("def", "set", "new"):
                if 'device' not in attr.keys():
                    return
                if 'name' not in attr.keys():
                    return
                self._rootElement = etree.Element(name, **dict(attr))
                self._currentElement = self._rootElement

            elif name == 'delProperty':
                if 'device' not in attr.keys():
                    return
                self._rootElement = etree.Element(name, **dict(attr))
                self._currentElement = self._rootElement

            elif name == "message":
                self._currentMessage = etree.Element(name, **dict(attr))
        except Exception as e:
            logging.error(f'startElement({name},{attr}):{type(e)}{e}')
            raise

    def characters(self, content):
        try:
            if self._currentElement.text is None:
                self._currentElement.text = io.StringIO()
            else:
                self._currentElement.text.write(content)
        except Exception as e:
            logging.error(f'characters({content}):{type(e)}{e}')
            raise

    def endElement(self, name):
        try:
            if self._rootElement is None:
                return

            if name == self._rootElement.tag:
                self._is_child = False
                prefix = name[:3]
                if prefix == 'set':
                    self.set_property(self._rootElement)
                
                elif prefix == 'def':
                    self.def_property(self._rootElement)
                
                elif name == 'delProperty':
                    self.del_property(self._rootElement)
                    self._rootElement = None

                elif name == "message":
                    self.new_message(self._currentMessage)
                    self._currentMessage = None
                    self._rootElement = None

                self._rootElement = None

            elif name == self._currentElement.tag:
                self._currentElement = self._rootElement
        except Exception as e:
            logging.error(f'endElement({name}):{type(e)}{e}')
            raise


