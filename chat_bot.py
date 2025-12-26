import sys
import json
import requests
from PyQt6.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QTextEdit, QPushButton, QComboBox, QScrollArea, QFrame,
    QListWidget, QListWidgetItem, QFileDialog
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer, QEasingCurve, QPropertyAnimation, QPoint
from PyQt6.QtGui import QClipboard
import speech_recognition as sr
import pyttsx3
import uuid
import re
import os

try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None

# Optional docx reader
try:
    import docx
except Exception:
    docx = None

OLLAMA_API_URL = "http://localhost:11434"


# --- Worker: stream from /api/chat and emit chunks (message.content) ---
class OllamaWorker(QThread):
    response_chunk = pyqtSignal(str)
    full_response = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    typing_signal = pyqtSignal(bool)

    def __init__(self, model, messages):
        super().__init__()
        self.model = model
        self.messages = messages
        self._running = True

    def stop(self):
        self._running = False

    def run(self):
        self.typing_signal.emit(True)
        try:
            payload = {"model": self.model, "messages": self.messages, "stream": True}
            full = ""
            with requests.post(f"{OLLAMA_API_URL}/api/chat", json=payload, stream=True, timeout=120) as r:
                r.raise_for_status()
                for line in r.iter_lines():
                    if not self._running:
                        break
                    if not line:
                        continue
                    try:
                        data = json.loads(line.decode("utf-8"))
                    except Exception:
                        continue
  
                    # Newer Ollama chat streaming format
                    if isinstance(data, dict) and "message" in data and isinstance(data["message"], dict):
                        content = data["message"].get("content")
                        if content:
                            full += content
                            self.response_chunk.emit(content)

                    if isinstance(data, dict) and data.get("done", False):
                        break

            self.full_response.emit(full)
        except Exception as e:
            self.error_occurred.emit(str(e))
        finally:
            self.typing_signal.emit(False)


class VoiceThread(QThread):
    text_recognized = pyqtSignal(str)
    listening_status = pyqtSignal(bool)

    def __init__(self, recognizer):
        super().__init__()
        self.recognizer = recognizer
        self._active = True

    def stop_listening(self):
        self._active = False

    def run(self):
        self.listening_status.emit(True)
        try:
            with sr.Microphone() as src:
                self.recognizer.adjust_for_ambient_noise(src)
                while self._active:
                    try:
                        audio = self.recognizer.listen(src, timeout=3, phrase_time_limit=6)
                        text = self.recognizer.recognize_google(audio)
                        self.text_recognized.emit(text)
                    except Exception:
                        continue
        finally:
            self.listening_status.emit(False)


class TTSThread(QThread):
    finished_speaking = pyqtSignal()

    def __init__(self, engine, text):
        super().__init__()
        self.engine = engine
        self.text = text
        self._stopped = False

    def stop(self):
        self._stopped = True
        try:
            self.engine.stop()
        except Exception:
            pass

    def run(self):
        try:
            self.engine.say(self.text)
            self.engine.runAndWait()
        finally:
            self.finished_speaking.emit()


class AIAssistantApp(QWidget):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Local AI Assistant")
        self.resize(1100, 700)

        self.current_model = None
        self.chat_sessions = []  
        self.current_session_id = None

        self.ollama_worker = None
        self.voice_thread = None
        self.tts_thread = None
        self.recognizer = sr.Recognizer()
        self.tts_engine = pyttsx3.init()

        self._build_ui()
        self.load_models()
        self.start_new_chat(initial=True)

    def _build_ui(self):
        layout = QHBoxLayout(self)

        left_col = QVBoxLayout()
        self.new_chat_btn = QPushButton("➕ New Chat")
        self.new_chat_btn.clicked.connect(lambda: self.start_new_chat())
        left_col.addWidget(self.new_chat_btn)

        self.chat_list = QListWidget()
        self.chat_list.itemClicked.connect(self._on_chat_selected)
        left_col.addWidget(self.chat_list)

        self.upload_btn = QPushButton("📎 Upload File")
        self.upload_btn.clicked.connect(self.load_file)
        left_col.addWidget(self.upload_btn)

        self.voice_start_btn = QPushButton("🎤 Start Voice")
        self.voice_start_btn.clicked.connect(self.start_voice)
        left_col.addWidget(self.voice_start_btn)

        self.voice_stop_btn = QPushButton("⛔ Stop Voice")
        self.voice_stop_btn.clicked.connect(self.stop_voice)
        left_col.addWidget(self.voice_stop_btn)

        layout.addLayout(left_col, 1)

        right_col = QVBoxLayout()

        top_row = QHBoxLayout()
        self.model_dropdown = QComboBox()
        self.model_dropdown.currentIndexChanged.connect(self._on_model_selected)
        top_row.addWidget(self.model_dropdown)
        self.refresh_btn = QPushButton("Refresh Models")
        self.refresh_btn.clicked.connect(self.load_models)
        top_row.addWidget(self.refresh_btn)
        right_col.addLayout(top_row)

        self.status_label = QLabel("🔴 Offline")
        right_col.addWidget(self.status_label)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.chat_container = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_container)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.chat_container)
        right_col.addWidget(self.scroll_area, 10)

        input_row = QHBoxLayout()
        self.input_box = QTextEdit()
        self.input_box.setFixedHeight(48)
        input_row.addWidget(self.input_box)

        self.send_btn = QPushButton("Send")
        self.send_btn.clicked.connect(self.send_message)
        input_row.addWidget(self.send_btn)

        right_col.addLayout(input_row)

        layout.addLayout(right_col, 3)

    def load_models(self):
        self.model_dropdown.clear()
        self.status_label.setText("🟡 Fetching models...")
        try:
            r = requests.get(f"{OLLAMA_API_URL}/api/tags", timeout=5)
            r.raise_for_status()
            data = r.json()
            models = [m.get("name") for m in data.get("models", []) if m.get("name")]
            if models:
                self.model_dropdown.addItems(models)
                self.current_model = models[0]
                self.status_label.setText("🟢 Online - models loaded")
            else:
                self.status_label.setText("🟡 No models found")
                self.current_model = None
        except Exception as e:
            self.status_label.setText(f"🔴 Offline: {e}")
            self.current_model = None

    def _on_model_selected(self, idx):
        self.current_model = self.model_dropdown.currentText()

    def start_new_chat(self, initial=False):
        cid = str(uuid.uuid4())
        session = {"id": cid, "title": "New Chat", "messages": []}

        self.chat_sessions.insert(0, session)
        self.current_session_id = cid
        self._refresh_chat_list()
        self._clear_chat_display()
        if not initial:
            self._render_message("assistant", "Hello! How can I help you?")

    def _refresh_chat_list(self):
        self.chat_list.clear()
        for s in self.chat_sessions:
            item = QListWidgetItem(s.get("title", "Chat"))
            item.setData(Qt.ItemDataRole.UserRole, s["id"])
            self.chat_list.addItem(item)

    def _on_chat_selected(self, item):
        cid = item.data(Qt.ItemDataRole.UserRole)
        if cid == self.current_session_id:
            return
        self.current_session_id = cid
        self._clear_chat_display()
        session = self._get_session()
        for m in session.get("messages", []):
            self._render_message(m["role"], m["content"], initial=True)

    def _get_session(self):
        return next(s for s in self.chat_sessions if s["id"] == self.current_session_id)

    def _clear_chat_display(self):
        while self.chat_layout.count():
            it = self.chat_layout.takeAt(0)
            if it.widget():
                it.widget().deleteLater()

    def _render_message(self, role, text, initial=False):

        if not initial:
            session = self._get_session()
            session["messages"].append({"role": role, "content": text})
            if role == "user" and sum(1 for m in session["messages"] if m["role"] == "user") == 1:
                session["title"] = text[:30] + ("..." if len(text) > 30 else "")
                self._refresh_chat_list()

        bubble = QFrame()
        bl = QVBoxLayout(bubble)
        lbl = QLabel()
        lbl.setWordWrap(True)
        lbl.setText(self._format_html(text))
        bl.addWidget(lbl)

        ctrl = QHBoxLayout()
        ctrl.addStretch(1)
        copy_btn = QPushButton("📋 Copy")
        copy_btn.setFixedWidth(80)
        copy_btn.clicked.connect(lambda: QApplication.clipboard().setText(text))
        ctrl.addWidget(copy_btn)

        if role == "assistant":
            read_btn = QPushButton("🔊 Read")
            read_btn.setFixedWidth(80)
            stop_btn = QPushButton("⛔ Stop")
            stop_btn.setFixedWidth(80)
            stop_btn.setVisible(False)
            ctrl.addWidget(read_btn)
            ctrl.addWidget(stop_btn)

            def start_tts():
                self._stop_tts()
                clean = re.sub(r"<[^>]*>", "", text)
                self.tts_thread = TTSThread(self.tts_engine, clean)
                read_btn.setVisible(False)
                stop_btn.setVisible(True)
                self.tts_thread.finished_speaking.connect(lambda: (stop_btn.setVisible(False), read_btn.setVisible(True), setattr(self, 'tts_thread', None)))
                self.tts_thread.start()

            def stop_tts():
                self._stop_tts()
                stop_btn.setVisible(False)
                read_btn.setVisible(True)

            read_btn.clicked.connect(start_tts)
            stop_btn.clicked.connect(stop_tts)

        bl.addLayout(ctrl)

        row = QHBoxLayout()
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        if role == "assistant":
            row_layout.addWidget(bubble)
            row_layout.addStretch(1)
        else:
            row_layout.addStretch(1)
            row_layout.addWidget(bubble)

        self.chat_layout.addWidget(row_widget)

        anim = QPropertyAnimation(bubble, b"pos")
        anim.setDuration(160)
        anim.setStartValue(bubble.pos() + QPoint(20 if role == "assistant" else -20, 0))
        anim.setEndValue(bubble.pos())
        anim.setEasingCurve(QEasingCurve.Type.OutQuad)
        anim.start()

        QTimer.singleShot(60, self._scroll_bottom)

    def _format_html(self, t):
        s = re.sub(r"<", "&lt;", t)
        s = re.sub(r">", "&gt;", s)
        return s.replace("\n", "<br>")  

    def _scroll_bottom(self):
        self.scroll_area.verticalScrollBar().setValue(self.scroll_area.verticalScrollBar().maximum())

    def send_message(self):
        user_text = self.input_box.toPlainText().strip()
        if not user_text:
            return
        if not self.current_model:
            self._show_system("Select a model first")
            return

        session = self._get_session()
        session["messages"].append({"role": "user", "content": user_text})
        self._render_message("user", user_text)
        self.input_box.clear()

        placeholder_lbl = QLabel("")
        placeholder_lbl.setWordWrap(True)
        ph_bubble = QFrame()
        ph_layout = QVBoxLayout(ph_bubble)
        ph_layout.addWidget(placeholder_lbl)
        ph_row = QWidget()
        ph_row_layout = QHBoxLayout(ph_row)
        ph_row_layout.addWidget(ph_bubble)
        ph_row_layout.addStretch(1)
        self.chat_layout.addWidget(ph_row)
        QTimer.singleShot(60, self._scroll_bottom)

        if self.ollama_worker:
            try:
                self.ollama_worker.stop()
                self.ollama_worker.wait(200)
            except Exception:
                pass
            self.ollama_worker = None

        messages = session["messages"]
        self.ollama_worker = OllamaWorker(self.current_model, messages)

        def on_chunk(chunk):
            current = re.sub(r"<[^>]*>", "", placeholder_lbl.text())
            new_text = current + chunk
            placeholder_lbl.setText(self._format_html(new_text))
            self._scroll_bottom()

        self.ollama_worker.response_chunk.connect(on_chunk)
        self.ollama_worker.error_occurred.connect(lambda e: self._show_system(f"AI Error: {e}"))

        def on_full(full_text):
            try:
                last_idx = self.chat_layout.count() - 1
                if last_idx >= 0:
                    it = self.chat_layout.takeAt(last_idx)
                    if it and it.widget():
                        it.widget().deleteLater()
            except Exception:
                pass

            session["messages"].append({"role": "assistant", "content": full_text})
            self._render_message("assistant", full_text)
            self.ollama_worker = None

        self.ollama_worker.full_response.connect(on_full)
        self.ollama_worker.typing_signal.connect(lambda b: self.status_label.setText("🟡 AI typing..." if b else "🟢 Online"))
        self.ollama_worker.start()

    def _show_system(self, text):
        bubble = QFrame()
        bl = QVBoxLayout(bubble)
        lbl = QLabel(text)
        lbl.setWordWrap(True)
        bl.addWidget(lbl)
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.addStretch(1)
        row_layout.addWidget(bubble)
        row_layout.addStretch(1)
        self.chat_layout.addWidget(row_widget)
        QTimer.singleShot(60, self._scroll_bottom)

    def _stop_tts(self):
        try:
            if self.tts_thread and self.tts_thread.isRunning():
                self.tts_thread.stop()
                self.tts_thread.wait(200)
                self.tts_thread = None
        except Exception:
            pass

    def start_voice(self):
        if self.voice_thread and self.voice_thread.isRunning():
            return
        self.voice_thread = VoiceThread(self.recognizer)
        self.voice_thread.text_recognized.connect(lambda t: self.input_box.insertPlainText((" " + t) if self.input_box.toPlainText() else t))
        self.voice_thread.listening_status.connect(lambda s: self.status_label.setText("🎤 Listening..." if s else "🟢 Online"))
        self.voice_thread.start()

    def stop_voice(self):
        if self.voice_thread:
            self.voice_thread.stop_listening()
            self.voice_thread.wait(200)
            self.voice_thread = None

    def load_file(self):
        dlg = QFileDialog(self)
        dlg.setNameFilter("Documents (*.txt *.docx *.pdf);;All Files (*)")
        if dlg.exec() == QFileDialog.DialogCode.Accepted:
            f = dlg.selectedFiles()[0]
            ext = os.path.splitext(f)[1].lower()
            content = ""
            try:
                if ext == ".txt":
                    with open(f, "r", encoding="utf-8") as fh:
                        content = fh.read()
                elif ext == ".docx":
                    if docx is None:
                        self._show_system("python-docx not installed")
                        return
                    d = docx.Document(f)
                    content = "\n".join 
                elif ext == ".pdf":
                    if PdfReader is None:
                        self._show_system("PyPDF2 not installed")
                        return
                    reader = PdfReader(f)
                    for p in reader.pages:
                        try:
                            content += (p.extract_text() or "") + "\n" 
                        except Exception:
                            continue
                else:
                    self._show_system(f"Unsupported: {ext}")
                    return
                self.input_box.insertPlainText(content)
            except Exception as e:
                self._show_system(f"File read error: {e}")


if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = AIAssistantApp()
    w.show()
    sys.exit(app.exec())
