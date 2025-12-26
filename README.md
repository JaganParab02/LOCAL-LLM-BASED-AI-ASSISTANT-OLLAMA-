# 🧠 Local AI Assistant (Desktop App)

A **desktop-based Local AI Assistant** built using **Python + PyQt6** that connects to **Ollama** to run LLMs locally.
The application supports **multi-chat sessions, streaming AI responses, voice input, text-to-speech output, and document uploads** (TXT, PDF, DOCX).

This project allows users to interact with local AI models **without internet dependency for inference**, ensuring privacy and low latency.

---

## ✨ Features

* 🧠 **Local LLM Chat (via Ollama)**
* 🔄 **Streaming AI responses (real-time typing effect)**
* 💬 **Multiple chat sessions with history**
* 🎤 **Voice input using Speech Recognition**
* 🔊 **Text-to-Speech (Read AI responses aloud)**
* 📄 **Upload & read files** (`.txt`, `.pdf`, `.docx`)
* 📋 **Copy responses to clipboard**
* 🎨 **Smooth UI animations**
* 🔌 **Offline-first (except speech recognition)**

---

## 🏗️ Architecture Overview

* **Frontend/UI**: PyQt6
* **AI Backend**: Ollama REST API (`/api/chat`)
* **Voice Input**: Google Speech Recognition (via `speech_recognition`)
* **Voice Output**: `pyttsx3` (offline TTS)
* **Threading**: `QThread` for non-blocking UI
* **Streaming**: Server-Sent JSON chunks from Ollama

---

## 📦 Requirements

### 1️⃣ System Requirements

* OS: **Windows / Linux / macOS**
* Python **3.9+**
* Microphone (for voice input)
* Speakers (for TTS)

---

### 2️⃣ Install Ollama (Required)

This app **requires Ollama running locally**.

👉 Download & install Ollama:
[https://ollama.com](https://ollama.com)

After installation, pull a model:

```bash
ollama pull llama3
```

Make sure Ollama is running:

```bash
ollama serve
```

Default API used:

```
http://localhost:11434
```

---

### 3️⃣ Python Dependencies

Install all required Python libraries:

```bash
pip install PyQt6 requests speechrecognition pyttsx3 PyPDF2 python-docx pyaudio
```

⚠️ **Important (Windows users)**
If `pyaudio` fails:

```bash
pip install pipwin
pipwin install pyaudio
```

---

## 🚀 How to Run the Application

### Step 1: Clone / Download Project

Place `chat_bot.py` in a project folder.

### Step 2: Start Ollama

```bash
ollama serve
```

### Step 3: Run the App

```bash
python chat_bot.py
```

The **Local AI Assistant window** will open.

---

## 🧪 How to Use

### 🔹 Select AI Model

* Models are auto-loaded from Ollama
* Use the **dropdown** at the top to switch models

### 🔹 Start Chat

* Click **➕ New Chat**
* Type your question and press **Send**

### 🔹 Voice Input

* Click **🎤 Start Voice**
* Speak naturally
* Click **⛔ Stop Voice** to stop listening

### 🔹 Text-to-Speech

* Click **🔊 Read** on AI responses
* Click **⛔ Stop** to stop speaking

### 🔹 Upload Documents

Supported:

* `.txt`
* `.pdf`
* `.docx`

Uploaded content is inserted into the input box for querying.

---

## 📁 Supported File Types

| File Type | Support                  |
| --------- | ------------------------ |
| `.txt`    | ✅                        |
| `.pdf`    | ✅ (PyPDF2 required)      |
| `.docx`   | ✅ (python-docx required) |
| Others    | ❌                        |

---

## 🛠️ Build Executable (Optional)

To convert into a standalone `.exe` (Windows):

### Install PyInstaller

```bash
pip install pyinstaller
```

### Build

```bash
pyinstaller --onefile --windowed chat_bot.py
```

Output will be in:

```
dist/chat_bot.exe
```

---

## ⚠️ Common Issues & Fixes

### ❌ Ollama Offline

**Error:** `🔴 Offline`

* Make sure Ollama is running
* Check: `http://localhost:11434/api/tags`

---

### ❌ No Models Found

Run:

```bash
ollama pull llama3
```

---

### ❌ Microphone Not Working

* Ensure mic permission is enabled
* Test mic in system settings
* Install correct `pyaudio`

---

### ❌ PDF/DOCX Not Reading

Install missing libs:

```bash
pip install PyPDF2 python-docx
```

---

## 🔐 Privacy & Security

* AI runs **100% locally**
* No chat data is uploaded
* Only voice recognition uses Google Speech API

---

