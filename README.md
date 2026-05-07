# QuizNova

QuizNova is a desktop quiz application built with Python and CustomTkinter.

It now supports two main workflows:

- `Paper Generator`: Create randomized PDF question papers and a master answer key.
- `OMR Correction`: Generate printable OMR sheets, upload scanned answer sheets, and evaluate candidates automatically.
- `AI Smart Quiz`: Generate a Gemini-powered quiz, answer it inside the app, get your score, see topic-wise performance, and identify weak topics to improve.

## Install

```bash
pip install -r requirements.txt
```

## Run

```bash
python quiz_generator.py
```

## AI Smart Quiz Setup

To use the AI quiz feature, add your Gemini API key in one of these ways:

- Add it to `.env` as `GEMINI_API_KEY=your_key_here`
- Paste it into the `Gemini API Key` field inside the app
- Set an environment variable named `GEMINI_API_KEY`

## Features

- Desktop GUI with `CustomTkinter`
- Gemini-powered quiz generation
- Automatic scoring and evaluation
- Weak-topic detection
- Detailed answer review with explanations
- Exportable performance report
- PDF quiz paper generation using `ReportLab`
- Printable OMR sheets with answer bubbles and sketch/rough-work space
- OMR answer-sheet correction from scanned image uploads using Pillow-based OCR-style image processing

## OMR Workflow

1. Generate question papers from the `Paper Generator` tab.
2. The app creates `Paper_*.pdf`, `OMR_Sheet_Paper_*.pdf`, `Master_Answer_Key.pdf`, and `OMR_Answer_Key.json`.
3. Print the matching OMR sheet for each candidate.
4. After the test, scan or photograph the completed sheet as a JPG/PNG image. Do not upload the blank PDF sheet directly.
5. Click `Upload OMR Sheet for Correction`, select `OMR_Answer_Key.json`, choose the scanned sheet, and enter the paper number.

Image uploads work with the listed requirements. PDF scan upload needs PyMuPDF, which may not be available on Python 3.14, so JPG/PNG is the recommended format.

## 📸 Screenshots

### 📝 Quiz Generator UI
![Quiz UI](screenshots/paper_generator.jpeg)

### 🤖 AI Smart Quiz
![AI Quiz](screenshots/quiz_preference.jpeg)

### 📊 Performance Report
![Report](screenshots/generated_quiz.jpeg)
![Report](screenshots/quiz_output.jpeg)
