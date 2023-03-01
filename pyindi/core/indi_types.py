#!/usr/bin/env python
# -*-coding:utf-8 -*-
'''
@File      :   pyindi/core/indi_types.py
@Time      :   2023/03
@Author    :   Stefano Sartor
@Version   :   0.1
@Contact   :   sartor@oavda.it
@License   :   MIT
@Copyright :   (C) 2023 FONDAZIONE CLÉMENT FILLIETROZ-ONLUS
'''


from enum import Enum
from collections import OrderedDict
import datetime
import base64
import io

IPS = Enum('IPS',{'Idle':'Idle','Ok':'Ok','Busy':'Busy','Alert':'Alert'})
ISS = Enum('ISS',{'Off':'Off','On':'On'})

class INTERFACE(Enum):
    GENERAL       = 0    
    TELESCOPE     = (1 << 0)
    CCD           = (1 << 1)
    GUIDER        = (1 << 2)
    FOCUSER       = (1 << 3)
    FILTER        = (1 << 4)
    DOME          = (1 << 5)
    GPS           = (1 << 6)
    WEATHER       = (1 << 7)
    AO            = (1 << 8)
    DUSTCAP       = (1 << 9)
    LIGHTBOX      = (1 << 10)
    DETECTOR      = (1 << 11)
    ROTATOR       = (1 << 12)
    SPECTROGRAPH  = (1 << 13)
    CORRELATOR    = (1 << 14)
    AUX           = (1 << 15)
    SENSOR        = SPECTROGRAPH | DETECTOR | CORRELATOR

class VectorProperty:
    def __init__(self) -> None:
        self.tag_vec = ''
        self.tag_ch = ''
        self.device=''
        self.name = ''
        self.state = IPS.Idle
        self.timestamp = None
        self.timeout = 0
        self.items = OrderedDict()

    def __repr__(self) -> str:
        return f'<{self.device}.{self.name}>{{{self.state} [{self.child_str()}]}}'

    def from_xml(self,ele):
        self.tag_vec = ele.tag
        self.device = ele.attrib['device']
        self.name = ele.attrib['name']
        self.state = IPS[ele.attrib['state']]
        if ele.attrib.get('timestamp') is not None:
            self.timestamp = datetime.datetime.fromisoformat(ele.attrib['timestamp'])
        if ele.attrib.get('timeout') is not None:
            self.timeout = int(ele.attrib['timeout'])


    def to_xml(self) -> str:
        tag = 'new'+self.tag_vec[3:]
        now = datetime.datetime.now().isoformat()
        xml = f'<{tag} device="{self.device}" name="{self.name}" timestamp="{now}">'
        xml += self.to_xml_child()
        xml += f'</{tag}>'
        return xml

    def to_xml_child(self) -> str:
        return ''

    def child_str(self) -> str:
        return ''


class NumberVectorProperty(VectorProperty):
    def __init__(self) -> None:
        super().__init__()
        self.tag_vec = 'newNumberVector'
        self.tag_ch = 'oneNumber'

    def from_xml(self, ele):
        super().from_xml(ele)
        for child in ele:
            child.text.seek(0)
            s = child.text.read()
            self.items[child.attrib['name']] = float(s.strip())

    def to_xml_child(self) -> str:
        xml = ''
        for k,v in self.items.items():
            xml += f'<{self.tag_ch} name="{k}">{v:.10f}</{self.tag_ch}>'
        return xml

    def child_str(self) -> str:
        s = ''
        for k,v in self.items.items():
            s += f'{k}:{v:.2f}, '
        return s

class SwitchVectorProperty(VectorProperty):
    def __init__(self) -> None:
        super().__init__()
        self.tag_vec = 'newSwitchVector'
        self.tag_ch = 'oneSwitch'

    def from_xml(self, ele):
        super().from_xml(ele)
        for child in ele:
            child.text.seek(0)
            s = child.text.read()
            self.items[child.attrib['name']] = ISS[s.strip()]

    def to_xml_child(self) -> str:
        xml = ''
        for k,v in self.items.items():
            xml += f'<{self.tag_ch} name="{k}">{v.value}</{self.tag_ch}>'
        return xml

    def child_str(self) -> str:
        s = ''
        for k,v in self.items.items():
            s += f'{k}:{v.value}, '
        return s

class TextVectorProperty(VectorProperty):
    def __init__(self) -> None:
        super().__init__()
        self.tag_vec = 'newTextVector'
        self.tag_ch = 'oneText'

    def from_xml(self, ele):
        super().from_xml(ele)
        for child in ele:
            if child.text is None:
                self.items[child.attrib['name']] = None
            else:
                child.text.seek(0)
                s = child.text.read()                
                self.items[child.attrib['name']] = s.strip()

    def to_xml_child(self) -> str:
        xml = ''
        for k,v in self.items.items():
            xml += f'<{self.tag_ch} name="{k}">{v}</{self.tag_ch}>'
        return xml

    def child_str(self) -> str:
        s = ''
        for k,v in self.items.items():
            s += f'{k}:{v}, '
        return s

class LightVectorProperty(VectorProperty):
    def __init__(self) -> None:
        super().__init__()
        self.tag_vec = 'setLightVector'
        self.tag_ch = 'oneLight'

    def from_xml(self, ele):
        super().from_xml(ele)
        for child in ele:
            child.text.seek(0)
            s = child.text.read()
            self.items[child.attrib['name']] = IPS[s.strip()]

    def to_xml(self) -> str:
        # we cannot write Lights...
        return ''

    def child_str(self) -> str:
        s = ''
        for k,v in self.items.items():
            s += f'{k}:{v.value}, '
        return s

class BLOBVectorProperty(VectorProperty):
    def __init__(self) -> None:
        super().__init__()
        self.tag_vec = 'newBlobVector'
        self.tag_ch = 'oneBlob'

    def from_xml(self, ele):
        super().from_xml(ele)
        for child in ele: 
            data = io.BytesIO()
            if child.text is not  None:
                child.text.seek(0)
                data.write(base64.b64decode(child.text.read()))
                data.seek(0)
               
            self.items[child.attrib['name']] = {
                'size':int(child.attrib.get('size','0')),
                'format':child.attrib.get('format','.dat'),
                'data':data
            }
            
    def to_xml_child(self) -> str:
        xml = ''
        for k,i in self.items.items():
            d = i['data']
            d.seek(0)
            data64 = base64.b64encode(d.read())
            xml += f'<{self.tag_ch} name="{k}" size="{i["size"]}" format="{i["format"]}">{data64}</{self.tag_ch}>'
        return xml

    def child_str(self) -> str:
        s = ''
        for k,i in self.items.items():
            s += f'{k}:{i["size"]}bytes, '
        return s

def vector_factory(ele) -> VectorProperty:
    vec = None
    name = ele.tag[3:]
    if name == 'NumberVector':
        vec = NumberVectorProperty()
    elif name == 'SwitchVector':
        vec = SwitchVectorProperty()
    elif name == 'TextVector':
        vec = TextVectorProperty()
    elif name == 'LightVector':
        vec = LightVectorProperty()
    elif name == 'BLOBVector':
        vec = BLOBVectorProperty()
    else:
        return None

    vec.from_xml(ele)
    return vec
