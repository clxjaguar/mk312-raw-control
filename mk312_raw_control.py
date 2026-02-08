#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
# https://github.com/clxjaguar/mk312-raw-control
#
# This program is free software: you can redistribute it
# and/or modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation, either version 3 of
# the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import sys, time, enum
from PyQt6.QtGui import *
from PyQt6.QtCore import *
from PyQt6.QtWidgets import *
from PyQt6.QtSerialPort import * # apt install python3-pyqt6.qtserialport

class GUI(QWidget):
	class ConnStates(enum.Enum):
		UNDEFINED = 0
		CONNECTING = 1
		ZERO_BYTE_SENT = 2
		LINK_BYTE_SENT = 3
		CONNECTION_ESTABLISHED = 4

	def __init__(self):
		super().__init__()
		self.connState = self.ConnStates.UNDEFINED;
		self.serialPortPicker = SerialPortPicker()
		self.serialPortPicker.openPort.connect(self.openPort)
		self.serialPortPicker.closePort.connect(self.closePort)
		self.serialPort = QSerialPort()
		self.serialPort.setBaudRate(19200)
		self.serialPort.errorOccurred.connect(self.errorOccurred)
		self.serialPort.baudRateChanged.connect(lambda x: print("baudRateChanged", x))
		self.serialPort.requestToSendChanged.connect(lambda x: print("requestToSendChanged", x))
		self.serialPort.dataTerminalReadyChanged.connect(lambda x: print("dataTerminalReadyChanged", x))
		self.initUi()

	def initUi(self):
		self.setStyleSheet("QLabel#Value { font-size: 18px; } "\
		                   "QLabel#Channel { font-size: 22px; } "\
		                   "QPushButton::checked#Gate { background-color: #ff6050; } "\
		                   "QToolButton:enabled:checked#PulseShape { background-color: #00c0ff; } "\
		                   "QGroupBox { border: 1px solid #707070; border-radius: 6px; padding: 0px; }")

		mainLayout = QVBoxLayout(self)
		mainLayout.addLayout(self.serialPortPicker)
		gl = QGridLayout()
		mainLayout.addLayout(gl)
		l2 = QHBoxLayout()
		l2.addWidget(QLabel("Ramp:"))
		self.rampSb = QSpinBox()
		self.rampSb.setToolTip("Ramp value is for both channels")
		self.rampSb.setRange(0, 255)
		self.rampSb.setValue(255)
		self.rampSb.valueChanged.connect(self.rampChanged)
		l2.addWidget(self.rampSb)
		l2.addStretch()
		self.ledOk = LED(color=(0, 255, 0), size=25)
		l2.addWidget(QLabel("Response: OK"))
		l2.addWidget(self.ledOk)
		self.ledError = LED(color=(255, 0, 0), size=25)
		l2.addWidget(QLabel("ERR"))
		l2.addWidget(self.ledError)
		gl.addLayout(l2, 0, 0, 1, 2)

		self.chansCtrlWidget = (ChannelRegistersControls("Channel A", [0x9d, 0x40, 0x04, 0x00], []), ChannelRegistersControls("Channel B", [0x9d, 0x40, 0x0a], [0x00]))
		for i, w in enumerate(self.chansCtrlWidget):
			w.channelChanged.connect(self.sendChannelFrame)
			gl.addWidget(w, 1, i)
			w.setEnabled(False)

		self.setWindowTitle("MK312 Raw Controls")
		self.show()
		self.readResponseTimer = QTimer()
		self.readResponseTimer.timeout.connect(self.readResponse)

	def openPort(self, portName):
		self.serialPort.setPortName(portName)
		r = self.serialPort.open(QSerialPort.OpenModeFlag.ReadWrite)
		if r:
			self.serialPort.write(b'\x00')
			self.connState = self.ConnStates.ZERO_BYTE_SENT
			self.readResponseTimer.start(100)

	def closePort(self):
		self.readResponseTimer.stop()
		self.serialPort.close()
		for w in self.chansCtrlWidget:
			w.setEnabled(False)

	def errorOccurred(self, error):
		if error.value != 0:
			if self.serialPort.isOpen():
				self.serialPort.close()
			self.readResponseTimer.stop()
			self.serialPortPicker.reset()
			QMessageBox.critical(self, "Error", "%s: %s" % (self.serialPort.portName(), error.name))

	def readResponse(self):
		l = self.serialPort.bytesAvailable()
		if l:
			d = self.serialPort.read(l)
			print("Received:", d.hex(), self.connState)

			match self.connState:
				case self.ConnStates.ZERO_BYTE_SENT:
					if b'\x07' in d:
						self.serialPort.write(b'\x0e')
						self.connState = self.ConnStates.LINK_BYTE_SENT

				case self.ConnStates.LINK_BYTE_SENT:
					if d == b'\x05':
						for w in self.chansCtrlWidget:
							w.setEnabled(True)
							self.sendChannelFrame(w)
						self.connState = self.ConnStates.CONNECTION_ESTABLISHED
					else:
						self.ledError.pulse()

				case self.ConnStates.CONNECTION_ESTABLISHED:
					if b'\x06' in d:
						self.ledOk.pulse()
					if b'\x07' in d:
						self.ledError.pulse()

	def rampChanged(self, value):
		for w in self.chansCtrlWidget:
			w.rampValue = value
			if self.connState == self.ConnStates.CONNECTION_ESTABLISHED:
				self.sendChannelFrame(w)

	def sendChannelFrame(self, channelWidget):
		a = channelWidget.readArray()
		a.append(sum(a) % 256)
		b = bytes(a)
		print(b.hex())
		self.serialPort.write(b)

	def keyPressEvent(self, event):
		if event.key() == Qt.Key.Key_Escape:
			self.close()
		self.handleKeyCode(event.nativeScanCode(), True)

	def keyReleaseEvent(self, event):
		self.handleKeyCode(event.nativeScanCode(), False)

	def handleKeyCode(self, keyCode, isPressed):
		match keyCode:
			case 0x25|0xa2: # XK_Control_L or VK_LCONTROL
				channel = 0
			case 0x32|0xa0: # XK_Shift_L or VK_LSHIFT
				channel = 1
			case 0x69|0xa3: # XK_Control_R or VK_RCONTROL
				channel = 1

			case _:
				return

		self.chansCtrlWidget[channel].gateBtn.setChecked(isPressed)
		if self.connState == self.ConnStates.CONNECTION_ESTABLISHED:
			self.sendChannelFrame(self.chansCtrlWidget[channel])

class ChannelRegistersControls(QGroupBox):
	channelChanged = pyqtSignal(QWidget)

	def __init__(self, chanName, prefixBytes, suffixBytes):
		super().__init__()
		self.prefixBytes, self.suffixBytes = prefixBytes, suffixBytes
		self.rampValue = 255
		l = QVBoxLayout(self)
		w = QLabel(chanName)
		w.setObjectName("Channel")
		w.setAlignment(Qt.AlignmentFlag.AlignCenter)
		l.addWidget(w)

		self.intensityDial  = MyDial(chanName, "Intensity")
		self.frequencyDial  = MyDial(chanName, "Frequency", revScale=True)
		self.pulseWidthDial = MyDial(chanName, "Pulse Width")
		self.pulseShapeBtns = [QToolButton() for i in range(3)]

		for w, value, icon in zip(self.pulseShapeBtns, (6, 4, 2), (ICON1, ICON2, ICON3)):
			w.setCheckable(True)
			w.setObjectName("PulseShape")
			w.value = value
			w.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
			w.setIcon(getEmbeddedIcon(icon))
			w.clicked.connect(self.pulseShapeBtnClicked)

		self.pulseShapeBtns[0].setChecked(True)
		self.gateBtn = QPushButton("Gate")
		self.gateBtn.setObjectName("Gate")
		self.gateBtn.setCheckable(True)

		for w in (self.intensityDial, self.frequencyDial, self.pulseWidthDial):
			l.addWidget(w)
			w.valueChanged.connect(self.paramChanged)
			l.addStretch()

		l2 = QHBoxLayout()
		for w in self.pulseShapeBtns:
			l2.addWidget(w)
		l.addLayout(l2)

		self.gateBtn.clicked.connect(self.paramChanged)
		l.addWidget(self.gateBtn)

	def pulseShapeBtnClicked(self, btn):
		for w in self.pulseShapeBtns:
			w.setChecked(True if w is self.sender() else False)
		self.channelChanged.emit(self)

	def paramChanged(self):
		self.channelChanged.emit(self)

	def readArray(self):
		b = self.prefixBytes.copy()
		gateValue = 1 if self.gateBtn.isChecked() else 0
		for w in self.pulseShapeBtns:
			if w.isChecked():
				gateValue+=w.value
				break

		b.append(gateValue)
		b.append(self.rampValue)
		# ~ for w in (self.rampDial, self.intensityDial, self.frequencyDial, self.pulseWidthDial):
		for w in (self.intensityDial, self.frequencyDial, self.pulseWidthDial):
			b.append(w.value())
		for v in self.suffixBytes:
			b.append(v)

		return b

class MyDial(QWidget):
	valueChanged = pyqtSignal(int)

	def __init__(self, chanName, title, min=0, max=255, revScale=False, defaultVal=127):
		super().__init__()
		self.revScale = revScale
		l = QVBoxLayout(self)
		l.setContentsMargins(0, 0, 0, 0)
		l.setSpacing(0)
		self.titleLabel = QLabel(title)
		self.titleLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
		l.addWidget(self.titleLabel)
		self.valueLabel = QLabel()
		self.valueLabel.setObjectName("Value")
		self.valueLabel.setAlignment(Qt.AlignmentFlag.AlignCenter)
		l.addWidget(self.valueLabel)
		self.dialWidget = QDial()
		self.dialWidget.setToolTip("%s: %s" % (chanName, title))
		self.dialWidget.setRange(min, max)
		self.dialWidget.setNotchTarget(15)
		self.dialWidget.setNotchesVisible(True)
		self.dialWidget.valueChanged.connect(self._valueChanged)
		l.addWidget(self.dialWidget)
		self.setValue(defaultVal)

	def _valueChanged(self, value):
		if self.revScale and value != 0:
			value = 256-value
		self.val = value
		self.valueLabel.setText("%d" % value)
		self.valueChanged.emit(value)

	def setValue(self, value):
		self.val = value
		self.valueLabel.setText("%d" % value)
		if self.revScale and value != 0:
			value = 256-value
		self.dialWidget.setValue(value)

	def value(self):
		return self.val


class SerialPortPicker(QHBoxLayout):
	openPort = pyqtSignal(str)
	closePort = pyqtSignal()

	def __init__(self):
		QHBoxLayout.__init__(self)
		self.open = False

		self.refreshBtn = QToolButton()
		self.refreshBtn.setText(u"↻")
		self.refreshBtn.clicked.connect(self.refreshSerial)
		self.addWidget(self.refreshBtn)

		self.serialDeviceCombo = QComboBox()
		self.serialDeviceCombo.setEditable(True)
		self.serialDeviceCombo.currentTextChanged.connect(self.serialDeviceChanged)
		self.addWidget(self.serialDeviceCombo)

		self.openBtn = QPushButton("Open")
		self.openBtn.setDisabled(True)
		self.openBtn.clicked.connect(self.openPortClicked)
		self.addWidget(self.openBtn)
		self.closeBtn = QPushButton("Close")
		self.closeBtn.clicked.connect(self.closePortClicked)
		self.closeBtn.setDisabled(True)
		self.addWidget(self.closeBtn)
		self.refreshSerial()

	def serialDeviceChanged(self, text):
		self.openBtn.setDisabled(False if text.strip() != "" else True)

	def refreshSerial(self):
		self.serialDeviceCombo.clear()
		self.serialDeviceCombo.insertItems(0, self.listSerialPorts())
		self.serialDeviceCombo.setCurrentIndex(-1)

	def listSerialPorts(self):
		result = []
		for port in QSerialPortInfo.availablePorts():
			# ~ print("%s %x:%x %s %s" % (port.portName(), port.vendorIdentifier(), port.productIdentifier(), port.manufacturer(), port.systemLocation() ))
			result.append(port.systemLocation())
		return result

	def addPort(self, portName):
		if portName not in [self.serialDeviceCombo.itemText(i) for i in range(self.serialDeviceCombo.count())]:
			self.serialDeviceCombo.addItem(portName)
			self.serialDeviceCombo.setCurrentIndex(self.serialDeviceCombo.count()-1)

	def setSelectEnabled(self, enableFlag=True):
		self.refreshBtn.setDisabled(not enableFlag)
		self.serialDeviceCombo.setDisabled(not enableFlag)
		self.closeBtn.setDisabled(enableFlag)
		self.openBtn.setDisabled(not enableFlag)
		self.openBtn.setFocus()

	def openPortClicked(self):
		portName = self.serialDeviceCombo.currentText()
		self.setSelectEnabled(False)
		self.openPort.emit(portName)
		self.open = True

	def closePortClicked(self):
		self.closePort.emit()
		self.setSelectEnabled(True)
		self.open = False

	def reset(self):
		self.setSelectEnabled(True)
		self.open = False


class LED(QLabel):
	def __init__(self, size=20, color=(0, 255, 0), text="", enabled=False):
		QLabel.__init__(self, text)
		self.pulseTimer = QTimer()
		self.pulseTimer.setSingleShot(True)
		self.pulseTimer.timeout.connect(self.disable)
		self.color = color
		self.size = size
		self.enabled = enabled
		self.setFixedSize(size, size)
		self.setAlignment(Qt.AlignmentFlag.AlignCenter)
		self.update()

	def enable(self, enabled=True):
		self.enabled = enabled
		self.update()

	def disable(self):
		self.enabled = False
		self.update()

	def pulse(self, durationMs=500):
		self.pulseTimer.start(durationMs)
		self.enable()

	def setColor(self, color, enabled=None):
		self.color = color
		if enabled != None:
			self.enabled = enabled
		self.update()

	def update(self):
		r1, g1, b1 = self.color
		r2, g2, b2 = self.color
		if not self.enabled:
			if r1 == 0 or r1 == 0 or r1 == 0: r1, g1, b1 = r1/4, g1/6, b1/2.5; r2, g2, b2 = r2/10, g2/12, b2/6
			else: r1, g1, b1 = r1/4, g1/4, b1/4; r2, g2, b2 = r2/10, g2/10, b2/10
		else:
			r1, g1, b1 = min(255, r1+80), min(255, g1+80), min(255, b1+80)

		self.setStyleSheet("margin: 0px; padding: 0px; color: black; border-radius: %.0f; background-color: qlineargradient(spread:pad, x1:0.145, y1:0.16, x2:1, y2:1, stop:0 rgba(%d, %d, %d, 255), stop:1 rgba(%d, %d, %d, 255));" % (self.size / 2, r1, g1, b1, r2, g2, b2))



def main():
	app = QApplication(sys.argv)
	w = GUI()
	sys.exit(app.exec())

def getEmbeddedIcon(s):
	qpm = QPixmap()
	icon = QIcon()
	qba_s = QByteArray(bytes(s.encode()))
	qba = QByteArray.fromBase64(qba_s)
	qpm.convertFromImage(QImage.fromData(qba.data(), 'PNG'))
	icon.addPixmap(qpm)
	return icon

ICON1 = "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAAXNSR0IB2cksfwAAAARnQU1BAACx\
         jwv8YQUAAAAgY0hSTQAAeiYAAICEAAD6AAAAgOgAAHUwAADqYAAAOpgAABdwnLpRPAAAAF1JREFU\
         OMu1U0EOACAIgub/v2yntlZmlsXRSYIkAUBVFRuQpFWXrmFJ9t4vSEK8aZ4qVwEjzGcWIgl09qZe\
         OVBr7uWJhSti4wlPPQxppS2UTALmT4xs/u8tRK+woQKQ7B8wqd5T1gAAAABJRU5ErkJggg=="

ICON2 = "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAAXNSR0IB2cksfwAAAARnQU1BAACx\
         jwv8YQUAAAAgY0hSTQAAeiYAAICEAAD6AAAAgOgAAHUwAADqYAAAOpgAABdwnLpRPAAAAEhJREFU\
         OMvtkTEOACAMAsH0/1/G1UGx0Q4O3tiUFgIBQJKwgSRn8xgWlmJ3v+GScN+cK+uAGWVZhEwDrqnI\
         uHU7JRGO+v+8RAcMjRgavqFGLgAAAABJRU5ErkJggg=="

ICON3 = "iVBORw0KGgoAAAANSUhEUgAAABAAAAAQCAYAAAAf8/9hAAAAAXNSR0IB2cksfwAAAARnQU1BAACx\
         jwv8YQUAAAAgY0hSTQAAeiYAAICEAAD6AAAAgOgAAHUwAADqYAAAOpgAABdwnLpRPAAAAExJREFU\
         OMvtkTEKACAMAz3p/79cJ0HE1kAHFzNfStK09vVeuLtLIBxZA67m1bfzvVrBsgZZuukzAkr5DUC5\
         gnwgSmTihPUE4Qrq/pEGkHkcGkagTsgAAAAASUVORK5CYII="


if __name__ == '__main__':
	main()
