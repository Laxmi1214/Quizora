import base64
import json
import mimetypes
import os
import random
import threading
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from dataclasses import dataclass

import customtkinter as ctk
import tkinter as tk
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import inch
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer
from reportlab.pdfgen import canvas
from tkinter import filedialog, messagebox, simpledialog

try:
    from PIL import Image, ImageOps
except ImportError:
    Image = None
    ImageOps = None

try:
    import fitz
except ImportError:
    fitz = None


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


def load_env_file(env_path: str = ".env") -> None:
    if not os.path.exists(env_path):
        return

    with open(env_path, "r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key and key not in os.environ:
                os.environ[key] = value


load_env_file()


@dataclass
class AIQuizQuestion:
    question: str
    options: list[str]
    answer: int
    topic: str
    explanation: str


ANSWER_LETTERS = ["A", "B", "C", "D"]
A4_WIDTH, A4_HEIGHT = A4
OMR_TOP_Y = A4_HEIGHT - 155
OMR_ROW_HEIGHT = 30
OMR_BUBBLE_X = [230, 282, 334, 386]
OMR_BUBBLE_RADIUS = 8
OMR_QUESTION_X = 60
OMR_SKETCH_X = 430
OMR_SKETCH_WIDTH = 110
OMR_SKETCH_HEIGHT = 22


class QuizNovaApp:
    def __init__(self) -> None:
        self.root = ctk.CTk()
        self.root.title("Quizora - Smart Quiz Generator")
        self.root.geometry("980x760")
        self.root.minsize(900, 700)

        self.manual_questions = []
        self.manual_current_question = 1
        self.total_q = 0
        self.per_paper = 0
        self.num_papers = 0
        self.exam_name = ""

        self.ai_questions = []
        self.ai_answer_vars = []
        self.latest_report_text = ""
        self.gemini_api_key = os.getenv("GEMINI_API_KEY", "")
        self.ai_quiz_window = None
        self.ai_quiz_report_textbox = None
        self.latest_answer_key_path = ""
        self.latest_omr_result_text = ""

        self.build_layout()

    def build_layout(self) -> None:
        self.root.grid_columnconfigure(0, weight=1)
        self.root.grid_rowconfigure(2, weight=1)

        title_label = ctk.CTkLabel(
            self.root,
            text="Quizora",
            font=ctk.CTkFont(family="Arial", size=30, weight="bold"),
        )
        title_label.grid(row=0, column=0, pady=(20, 6))

        subtitle_label = ctk.CTkLabel(
            self.root,
            text="Create printable quiz papers or generate AI-powered practice quizzes with topic-wise feedback.",
            font=ctk.CTkFont(size=14),
        )
        subtitle_label.grid(row=1, column=0, pady=(0, 10), padx=20, sticky="n")

        self.tab_view = ctk.CTkTabview(self.root, width=940, height=620)
        self.tab_view.grid(row=2, column=0, padx=20, pady=(0, 20), sticky="nsew")

        self.paper_tab = self.tab_view.add("Paper Generator")
        self.ai_tab = self.tab_view.add("AI Smart Quiz")

        self.paper_tab.grid_columnconfigure(0, weight=1)
        self.ai_tab.grid_columnconfigure(0, weight=1)

        self.build_paper_generator_tab()
        self.build_ai_quiz_tab()

    def build_paper_generator_tab(self) -> None:
        self.paper_setup_frame = ctk.CTkFrame(self.paper_tab)
        self.paper_setup_frame.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        self.paper_setup_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.paper_setup_frame,
            text="Create Randomized PDF Question Papers",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, columnspan=2, pady=(18, 8), padx=20, sticky="w")

        labels = [
            ("Exam Name:", "e.g. Midterm Math"),
            ("Total Questions to Create:", "e.g. 50"),
            ("Questions Per Paper:", "e.g. 10"),
            ("Number of Question Papers:", "e.g. 5"),
        ]
        self.paper_entries = []
        for index, (label_text, placeholder) in enumerate(labels, start=1):
            ctk.CTkLabel(
                self.paper_setup_frame,
                text=label_text,
                font=ctk.CTkFont(size=14),
            ).grid(row=index, column=0, pady=12, padx=20, sticky="w")
            entry = ctk.CTkEntry(
                self.paper_setup_frame,
                font=ctk.CTkFont(size=14),
                placeholder_text=placeholder,
            )
            entry.grid(row=index, column=1, pady=12, padx=20, sticky="ew")
            self.paper_entries.append(entry)

        self.exam_name_entry = self.paper_entries[0]
        self.total_questions_entry = self.paper_entries[1]
        self.questions_per_paper_entry = self.paper_entries[2]
        self.num_papers_entry = self.paper_entries[3]

        ctk.CTkButton(
            self.paper_setup_frame,
            text="Start Creating Questions",
            font=ctk.CTkFont(family="Arial", size=14, weight="bold"),
            command=self.start_manual_setup,
        ).grid(row=5, column=0, columnspan=2, padx=20, pady=(16, 18), sticky="ew")

        omr_frame = ctk.CTkFrame(self.paper_setup_frame)
        omr_frame.grid(row=6, column=0, columnspan=2, padx=20, pady=(0, 20), sticky="ew")
        omr_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            omr_frame,
            text="OMR Correction",
            font=ctk.CTkFont(size=18, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=(14, 4), sticky="w")

        ctk.CTkLabel(
            omr_frame,
            text="Upload a scanned OMR answer sheet PDF or image. AI OCR reads the marked answers and evaluates the candidate.",
            font=ctk.CTkFont(size=13),
            wraplength=780,
            justify="left",
        ).grid(row=1, column=0, padx=16, pady=(0, 10), sticky="w")

        action_row = ctk.CTkFrame(omr_frame, fg_color="transparent")
        action_row.grid(row=2, column=0, padx=16, pady=(0, 14), sticky="ew")
        action_row.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(
            action_row,
            text="Upload OMR Sheet for Correction",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.correct_omr_sheet,
        ).grid(row=0, column=0, padx=(0, 8), sticky="ew")

        ctk.CTkButton(
            action_row,
            text="Save Latest OMR Result",
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.save_omr_result,
        ).grid(row=0, column=1, padx=(8, 0), sticky="ew")

        self.paper_question_frame = None
        self.paper_question_text = None
        self.paper_option_entries = []
        self.paper_correct_answer_var = tk.StringVar(value="")

    def build_ai_quiz_tab(self) -> None:
        container = ctk.CTkFrame(self.ai_tab)
        container.grid(row=0, column=0, padx=20, pady=20, sticky="nsew")
        container.grid_columnconfigure(0, weight=1)
        container.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(
            container,
            text="AI-Powered Smart Quiz and Performance Analysis",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, padx=20, pady=(18, 8), sticky="w")

        form_frame = ctk.CTkFrame(container)
        form_frame.grid(row=1, column=0, padx=20, pady=(0, 14), sticky="ew")
        form_frame.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(form_frame, text="Subject:", font=ctk.CTkFont(size=14)).grid(row=0, column=0, padx=16, pady=10, sticky="w")
        self.ai_subject_entry = ctk.CTkEntry(form_frame, placeholder_text="e.g. Python, Biology, DBMS")
        self.ai_subject_entry.grid(row=0, column=1, padx=16, pady=10, sticky="ew")

        ctk.CTkLabel(form_frame, text="Difficulty:", font=ctk.CTkFont(size=14)).grid(row=0, column=2, padx=16, pady=10, sticky="w")
        self.ai_difficulty_menu = ctk.CTkOptionMenu(form_frame, values=["Beginner", "Intermediate", "Advanced"])
        self.ai_difficulty_menu.set("Intermediate")
        self.ai_difficulty_menu.grid(row=0, column=3, padx=16, pady=10, sticky="ew")

        ctk.CTkLabel(form_frame, text="Questions:", font=ctk.CTkFont(size=14)).grid(row=1, column=0, padx=16, pady=10, sticky="w")
        self.ai_num_questions_entry = ctk.CTkEntry(form_frame, placeholder_text="e.g. 8")
        self.ai_num_questions_entry.insert(0, "5")
        self.ai_num_questions_entry.grid(row=1, column=1, padx=16, pady=10, sticky="ew")

        ctk.CTkLabel(form_frame, text="Focus Topics:", font=ctk.CTkFont(size=14)).grid(row=2, column=0, padx=16, pady=10, sticky="w")
        self.ai_topics_entry = ctk.CTkEntry(form_frame, placeholder_text="e.g. loops, functions, SQL joins")
        self.ai_topics_entry.grid(row=2, column=1, columnspan=3, padx=16, pady=10, sticky="ew")

        ctk.CTkLabel(form_frame, text="Learning Goal / Prompt:", font=ctk.CTkFont(size=14)).grid(row=3, column=0, padx=16, pady=10, sticky="nw")
        self.ai_prompt_text = ctk.CTkTextbox(form_frame, height=90)
        self.ai_prompt_text.grid(row=3, column=1, columnspan=3, padx=16, pady=10, sticky="ew")
        self.ai_prompt_text.insert("1.0", "Generate a concept-based quiz that checks understanding and not just memory.")

        button_row = ctk.CTkFrame(form_frame, fg_color="transparent")
        button_row.grid(row=4, column=0, columnspan=4, padx=16, pady=(6, 16), sticky="ew")
        button_row.grid_columnconfigure((0, 1), weight=1)

        self.ai_generate_button = ctk.CTkButton(button_row, text="Generate AI Quiz", command=self.generate_ai_quiz)
        self.ai_generate_button.grid(row=0, column=0, padx=(0, 10), sticky="ew")

        self.ai_save_report_button = ctk.CTkButton(
            button_row,
            text="Save Latest Report",
            command=self.save_report,
            state="disabled",
        )
        self.ai_save_report_button.grid(row=0, column=1, padx=(10, 0), sticky="ew")

        self.ai_status_label = ctk.CTkLabel(
            container,
            text="Generate a quiz, answer it, and get a topic-wise performance report.",
            font=ctk.CTkFont(size=13),
        )
        self.ai_status_label.grid(row=2, column=0, padx=20, pady=(0, 10), sticky="w")

        self.ai_content_frame = ctk.CTkScrollableFrame(container, label_text="Quiz Workspace")
        self.ai_content_frame.grid(row=3, column=0, padx=20, pady=(0, 20), sticky="nsew")
        self.ai_content_frame.grid_columnconfigure(0, weight=1)

        self.ai_report_textbox = ctk.CTkTextbox(self.ai_content_frame, height=220)
        self.ai_report_textbox.grid(row=0, column=0, padx=10, pady=10, sticky="ew")
        self.ai_report_textbox.insert("1.0", "Your report will appear here after you submit a generated quiz.")
        self.ai_report_textbox.configure(state="disabled")

    def start_manual_setup(self) -> None:
        exam_name = self.exam_name_entry.get().strip()
        total_q = self.total_questions_entry.get().strip()
        per_paper = self.questions_per_paper_entry.get().strip()
        num_papers = self.num_papers_entry.get().strip()

        if not exam_name:
            messagebox.showerror("Error", "Please enter Exam Name!")
            return

        if not total_q.isdigit() or not per_paper.isdigit() or not num_papers.isdigit():
            messagebox.showerror("Error", "Please enter valid numbers!")
            return

        self.exam_name = exam_name
        self.total_q = int(total_q)
        self.per_paper = int(per_paper)
        self.num_papers = int(num_papers)

        if self.per_paper > self.total_q:
            messagebox.showerror("Error", "Questions per paper cannot exceed total questions!")
            return

        self.manual_questions = []
        self.manual_current_question = 1
        self.paper_setup_frame.grid_remove()
        self.show_manual_question_screen()

    def show_manual_question_screen(self) -> None:
        if self.paper_question_frame is not None:
            self.paper_question_frame.destroy()

        self.paper_question_frame = ctk.CTkFrame(self.paper_tab)
        self.paper_question_frame.grid(row=1, column=0, pady=(0, 20), padx=20, sticky="nsew")
        self.paper_question_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.paper_question_frame,
            text=f"Enter Question {self.manual_current_question} of {self.total_q}",
            font=ctk.CTkFont(family="Arial", size=18, weight="bold"),
        ).grid(row=0, column=0, pady=(20, 10))

        ctk.CTkLabel(self.paper_question_frame, text="Question Text:", font=ctk.CTkFont(size=14)).grid(
            row=1, column=0, sticky="w", padx=20
        )

        self.paper_question_text = ctk.CTkTextbox(self.paper_question_frame, height=90, font=ctk.CTkFont(size=14))
        self.paper_question_text.grid(row=2, column=0, padx=20, pady=(5, 15), sticky="ew")

        options_frame = ctk.CTkFrame(self.paper_question_frame, fg_color="transparent")
        options_frame.grid(row=3, column=0, padx=20, sticky="ew")
        options_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(options_frame, text="Correct", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=0, padx=(0, 10), sticky="w"
        )
        ctk.CTkLabel(options_frame, text="Option Text", font=ctk.CTkFont(size=14, weight="bold")).grid(
            row=0, column=1, sticky="w"
        )

        self.paper_option_entries = []
        self.paper_correct_answer_var = tk.StringVar(value="")

        for index in range(4):
            ctk.CTkRadioButton(
                options_frame,
                text="",
                variable=self.paper_correct_answer_var,
                value=str(index),
                width=30,
            ).grid(row=index + 1, column=0, pady=10, sticky="w")

            option_entry = ctk.CTkEntry(
                options_frame,
                font=ctk.CTkFont(size=14),
                placeholder_text=f"Option {chr(65 + index)}",
            )
            option_entry.grid(row=index + 1, column=1, pady=10, sticky="ew")
            self.paper_option_entries.append(option_entry)

        ctk.CTkButton(
            self.paper_question_frame,
            text="Save & Next" if self.manual_current_question < self.total_q else "Finish & Generate",
            font=ctk.CTkFont(family="Arial", size=14, weight="bold"),
            fg_color="#27ae60",
            hover_color="#219653",
            command=self.save_manual_question,
        ).grid(row=4, column=0, pady=20)

    def save_manual_question(self) -> None:
        question = self.paper_question_text.get("1.0", "end").strip()
        options = [entry.get().strip() for entry in self.paper_option_entries]
        correct_index = self.paper_correct_answer_var.get()

        if not question or "" in options or correct_index == "":
            messagebox.showerror("Error", "Please fill all fields and select the correct answer!")
            return

        self.manual_questions.append(
            {
                "question": question,
                "options": options,
                "answer": int(correct_index),
            }
        )

        if self.manual_current_question < self.total_q:
            self.manual_current_question += 1
            self.show_manual_question_screen()
            return

        messagebox.showinfo("Success", "All questions saved successfully.")
        if self.paper_question_frame is not None:
            self.paper_question_frame.destroy()
            self.paper_question_frame = None
        self.paper_setup_frame.grid()
        self.generate_papers()

    def generate_papers(self) -> None:
        save_folder = filedialog.askdirectory(title="Select folder to save question papers")

        if not save_folder:
            messagebox.showerror("Error", "No folder selected!")
            return

        styles = getSampleStyleSheet()
        normal_style = styles["Normal"]
        heading_style = styles["Heading1"]
        sub_heading = styles["Heading2"]

        answer_pdf_path = os.path.join(save_folder, "Master_Answer_Key.pdf")
        answer_doc = SimpleDocTemplate(answer_pdf_path, pagesize=A4)
        answer_elements = [
            Paragraph(self.exam_name, heading_style),
            Spacer(1, 0.2 * inch),
            Paragraph("MASTER ANSWER KEY", sub_heading),
            Spacer(1, 0.5 * inch),
        ]
        answer_key_data = {
            "exam_name": self.exam_name,
            "total_questions": self.total_q,
            "papers": {},
        }

        for paper_num in range(1, self.num_papers + 1):
            pdf_path = os.path.join(save_folder, f"Paper_{paper_num}.pdf")
            doc = SimpleDocTemplate(pdf_path, pagesize=A4)
            elements = []
            paper_answers = {}

            shuffled_questions = random.sample(self.manual_questions, len(self.manual_questions))
            question_index = 0
            page_number = 1

            while question_index < self.total_q:
                elements.extend(
                    [
                        Paragraph(self.exam_name, heading_style),
                        Spacer(1, 0.2 * inch),
                        Paragraph(f"Question Paper {paper_num}", sub_heading),
                        Spacer(1, 0.2 * inch),
                        Paragraph(f"Page {page_number}", normal_style),
                        Spacer(1, 0.4 * inch),
                    ]
                )

                page_questions = shuffled_questions[question_index : question_index + self.per_paper]

                for local_index, question_data in enumerate(page_questions):
                    options = question_data["options"][:]
                    correct_answer_text = options[question_data["answer"]]
                    random.shuffle(options)

                    elements.append(
                        Paragraph(
                            f"{question_index + local_index + 1}. {question_data['question']}",
                            normal_style,
                        )
                    )
                    elements.append(Spacer(1, 0.2 * inch))

                    for option_index, option_text in enumerate(options):
                        elements.append(Paragraph(f"{chr(65 + option_index)}. {option_text}", normal_style))
                        elements.append(Spacer(1, 0.1 * inch))

                    elements.append(Spacer(1, 0.3 * inch))
                    answer_elements.append(
                        Paragraph(
                            f"<b>Paper {paper_num} - Question {question_index + local_index + 1}</b>",
                            normal_style,
                        )
                    )
                    answer_elements.append(Spacer(1, 0.1 * inch))
                    answer_elements.append(Paragraph(question_data["question"], normal_style))
                    answer_elements.append(Spacer(1, 0.1 * inch))

                    for option_index, option_text in enumerate(options):
                        suffix = " <b>(Correct Answer)</b>" if option_text == correct_answer_text else ""
                        if option_text == correct_answer_text:
                            paper_answers[str(question_index + local_index + 1)] = chr(65 + option_index)
                        answer_elements.append(
                            Paragraph(f"{chr(65 + option_index)}. {option_text}{suffix}", normal_style)
                        )
                        answer_elements.append(Spacer(1, 0.05 * inch))

                    answer_elements.append(Spacer(1, 0.2 * inch))

                question_index += self.per_paper
                page_number += 1

                if question_index < self.total_q:
                    elements.append(PageBreak())

            doc.build(elements)
            answer_key_data["papers"][str(paper_num)] = paper_answers
            self.generate_omr_sheet(save_folder, paper_num, len(paper_answers))

        answer_doc.build(answer_elements)
        self.latest_answer_key_path = os.path.join(save_folder, "OMR_Answer_Key.json")
        with open(self.latest_answer_key_path, "w", encoding="utf-8") as key_file:
            json.dump(answer_key_data, key_file, indent=2)

        messagebox.showinfo(
            "Success",
            "Question papers, OMR sheets, master answer key, and OMR_Answer_Key.json generated successfully.",
        )

    def omr_rows_per_page(self) -> int:
        return int((OMR_TOP_Y - 70) // OMR_ROW_HEIGHT)

    def generate_omr_sheet(self, save_folder: str, paper_num: int, question_count: int) -> None:
        omr_path = os.path.join(save_folder, f"OMR_Sheet_Paper_{paper_num}.pdf")
        omr_canvas = canvas.Canvas(omr_path, pagesize=A4)
        rows_per_page = self.omr_rows_per_page()
        total_pages = max(1, (question_count + rows_per_page - 1) // rows_per_page)

        for page_index in range(total_pages):
            start_question = page_index * rows_per_page + 1
            end_question = min(question_count, (page_index + 1) * rows_per_page)

            omr_canvas.setFont("Helvetica-Bold", 16)
            omr_canvas.drawString(54, A4_HEIGHT - 42, self.exam_name or "Quizora Exam")
            omr_canvas.setFont("Helvetica-Bold", 13)
            omr_canvas.drawString(54, A4_HEIGHT - 66, f"OMR Answer Sheet - Paper {paper_num}")
            omr_canvas.setFont("Helvetica", 9)
            omr_canvas.drawRightString(A4_WIDTH - 54, A4_HEIGHT - 66, f"Page {page_index + 1} of {total_pages}")

            omr_canvas.setFont("Helvetica", 10)
            omr_canvas.drawString(54, A4_HEIGHT - 96, "Candidate Name:")
            omr_canvas.line(150, A4_HEIGHT - 98, 330, A4_HEIGHT - 98)
            omr_canvas.drawString(350, A4_HEIGHT - 96, "Roll No:")
            omr_canvas.line(402, A4_HEIGHT - 98, 540, A4_HEIGHT - 98)
            omr_canvas.drawString(
                54,
                A4_HEIGHT - 120,
                "Fill one bubble fully for each question. Use the sketch box for rough work or a short written response.",
            )

            omr_canvas.setStrokeColor(colors.black)
            omr_canvas.setFillColor(colors.black)
            omr_canvas.setFont("Helvetica-Bold", 9)
            omr_canvas.drawString(OMR_QUESTION_X, OMR_TOP_Y + 18, "Q.No")
            for option_index, option_x in enumerate(OMR_BUBBLE_X):
                omr_canvas.drawCentredString(option_x, OMR_TOP_Y + 18, ANSWER_LETTERS[option_index])
            omr_canvas.drawString(OMR_SKETCH_X, OMR_TOP_Y + 18, "Sketch / rough answer space")

            for row_index, question_number in enumerate(range(start_question, end_question + 1)):
                y = OMR_TOP_Y - row_index * OMR_ROW_HEIGHT
                omr_canvas.setFont("Helvetica", 10)
                omr_canvas.drawString(OMR_QUESTION_X, y - 3, str(question_number))

                for option_x in OMR_BUBBLE_X:
                    omr_canvas.circle(option_x, y, OMR_BUBBLE_RADIUS, stroke=1, fill=0)

                omr_canvas.rect(OMR_SKETCH_X, y - 12, OMR_SKETCH_WIDTH, OMR_SKETCH_HEIGHT, stroke=1, fill=0)
                omr_canvas.setStrokeColor(colors.lightgrey)
                omr_canvas.line(54, y - 16, A4_WIDTH - 54, y - 16)
                omr_canvas.setStrokeColor(colors.black)

            omr_canvas.showPage()

        omr_canvas.save()

    def correct_omr_sheet(self) -> None:
        key_path = self.latest_answer_key_path
        if not key_path or not os.path.exists(key_path):
            key_path = filedialog.askopenfilename(
                title="Select OMR_Answer_Key.json",
                filetypes=[("JSON Files", "*.json")],
            )
        if not key_path:
            return

        sheet_path = filedialog.askopenfilename(
            title="Select scanned OMR sheet",
            filetypes=[
                ("OMR Sheets", "*.pdf *.png *.jpg *.jpeg *.bmp *.tif *.tiff"),
                ("PDF Files", "*.pdf"),
                ("Image Files", "*.png *.jpg *.jpeg *.bmp *.tif *.tiff"),
            ],
        )
        if not sheet_path:
            return

        paper_num = simpledialog.askinteger("Paper Number", "Enter the paper number to evaluate:", minvalue=1)
        if paper_num is None:
            return

        try:
            with open(key_path, "r", encoding="utf-8") as key_file:
                key_data = json.load(key_file)

            answer_key = key_data["papers"].get(str(paper_num))
            if not answer_key:
                messagebox.showerror("Error", f"No answer key found for Paper {paper_num}.")
                return

            api_key = self.gemini_api_key or os.getenv("GEMINI_API_KEY")
            if not api_key:
                messagebox.showerror(
                    "Missing API Key",
                    "AI OCR correction needs your Gemini API key. Add it in .env as GEMINI_API_KEY or use the AI Smart Quiz tab.",
                )
                return

            try:
                detected_answers = self.request_gemini_omr_answers(
                    api_key=api_key,
                    sheet_path=sheet_path,
                    paper_num=paper_num,
                    question_count=len(answer_key),
                )
            except Exception as ai_exc:
                if sheet_path.lower().endswith(".pdf"):
                    raise RuntimeError(f"AI OCR could not read the PDF OMR sheet: {ai_exc}") from ai_exc

                if Image is None or ImageOps is None:
                    raise RuntimeError(
                        f"AI OCR failed and local image fallback needs Pillow: {ai_exc}"
                    ) from ai_exc

                page_images = self.load_omr_images(sheet_path)
                detected_answers = self.read_omr_answers(page_images, len(answer_key))

            self.show_omr_result(key_data.get("exam_name", ""), paper_num, answer_key, detected_answers)
        except Exception as exc:
            messagebox.showerror("OMR Correction Error", f"Could not correct the sheet.\n\n{exc}")

    def request_gemini_omr_answers(
        self,
        api_key: str,
        sheet_path: str,
        paper_num: int,
        question_count: int,
        model: str = "gemini-2.5-flash",
    ) -> dict:
        mime_type = self.get_omr_mime_type(sheet_path)
        with open(sheet_path, "rb") as sheet_file:
            encoded_file = base64.b64encode(sheet_file.read()).decode("utf-8")

        prompt = self.build_omr_ocr_prompt(paper_num, question_count)
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{urllib.parse.quote(model)}:generateContent?key={urllib.parse.quote(api_key)}"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": prompt},
                        {
                            "inline_data": {
                                "mime_type": mime_type,
                                "data": encoded_file,
                            }
                        },
                    ]
                }
            ]
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=90) as response:
                raw_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ValueError(f"Gemini AI OCR failed with HTTP {exc.code}: {error_body}") from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"Could not reach Gemini AI OCR: {exc.reason}") from exc

        data = json.loads(raw_body)
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini AI OCR returned no candidates.")

        parts = candidates[0].get("content", {}).get("parts", [])
        response_text = "\n".join(part.get("text", "") for part in parts if part.get("text"))
        if not response_text.strip():
            raise ValueError("Gemini AI OCR returned an empty response.")

        payload = self.extract_json_payload(response_text)
        answers = payload.get("answers", payload)
        return self.normalize_detected_answers(answers, question_count)

    def get_omr_mime_type(self, sheet_path: str) -> str:
        extension = os.path.splitext(sheet_path)[1].lower()
        extension_map = {
            ".pdf": "application/pdf",
            ".png": "image/png",
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".bmp": "image/bmp",
            ".tif": "image/tiff",
            ".tiff": "image/tiff",
        }
        return extension_map.get(extension) or mimetypes.guess_type(sheet_path)[0] or "application/octet-stream"

    def build_omr_ocr_prompt(self, paper_num: int, question_count: int) -> str:
        return f"""
You are correcting a filled OMR answer sheet for Quizora.

Task:
- Read the uploaded PDF/image document.
- Detect the marked answer bubble for each question.
- Valid options are A, B, C, and D.
- If no option is clearly marked, use "Blank/Unclear".
- If multiple options are marked for the same question, use "Blank/Unclear".
- Return strict JSON only. Do not include markdown fences or explanation.

Context:
- Paper number: {paper_num}
- Total questions: {question_count}
- The OMR sheet has question numbers and four bubbles labelled A, B, C, D.

Required JSON shape:
{{
  "answers": {{
    "1": "A",
    "2": "Blank/Unclear"
  }}
}}

Return answers for every question from 1 to {question_count}.
""".strip()

    def normalize_detected_answers(self, answers: dict, question_count: int) -> dict:
        normalized = {}
        for question_number in range(1, question_count + 1):
            raw_answer = answers.get(str(question_number), answers.get(question_number, "Blank/Unclear"))
            answer = str(raw_answer).strip().upper()
            if answer in ANSWER_LETTERS:
                normalized[str(question_number)] = answer
            else:
                normalized[str(question_number)] = "Blank/Unclear"
        return normalized

    def load_omr_images(self, sheet_path: str) -> list:
        if sheet_path.lower().endswith(".pdf"):
            if fitz is None:
                raise RuntimeError("PDF OMR upload needs PyMuPDF. Install it with: pip install pymupdf")

            document = fitz.open(sheet_path)
            images = []
            for page in document:
                pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
                page_image = Image.frombytes("RGB", [pixmap.width, pixmap.height], pixmap.samples)
                images.append(page_image)
            document.close()
            return images

        try:
            image = Image.open(sheet_path).convert("RGB")
        except Exception as exc:
            raise RuntimeError("The selected OMR image could not be opened.") from exc

        if image is None:
            raise RuntimeError("The selected OMR image could not be opened.")
        return [image]

    def read_omr_answers(self, page_images: list, question_count: int) -> dict:
        rows_per_page = self.omr_rows_per_page()
        detected_answers = {}

        for page_index, image in enumerate(page_images):
            gray = ImageOps.grayscale(image)
            gray = ImageOps.autocontrast(gray)
            width, height = gray.size

            for row_index in range(rows_per_page):
                question_number = page_index * rows_per_page + row_index + 1
                if question_number > question_count:
                    break

                option_scores = []
                for option_x in OMR_BUBBLE_X:
                    center_x = int(option_x / A4_WIDTH * width)
                    center_y = int((A4_HEIGHT - (OMR_TOP_Y - row_index * OMR_ROW_HEIGHT)) / A4_HEIGHT * height)
                    radius = max(5, int(OMR_BUBBLE_RADIUS / A4_WIDTH * width * 1.7))
                    crop = gray.crop(
                        (
                            max(0, center_x - radius),
                            max(0, center_y - radius),
                            min(width, center_x + radius),
                            min(height, center_y + radius),
                        )
                    )
                    dark_pixels = sum(1 for pixel in crop.getdata() if pixel < 120)
                    option_scores.append(dark_pixels)

                best_score = max(option_scores)
                second_score = sorted(option_scores)[-2]
                average_score = sum(option_scores) / len(option_scores)

                if best_score < max(30, average_score * 1.45) or best_score - second_score < 12:
                    detected_answers[str(question_number)] = "Blank/Unclear"
                else:
                    detected_answers[str(question_number)] = ANSWER_LETTERS[option_scores.index(best_score)]

        return detected_answers

    def show_omr_result(self, exam_name: str, paper_num: int, answer_key: dict, detected_answers: dict) -> None:
        correct_count = 0
        wrong_items = []
        blank_items = []

        for question_number, correct_answer in answer_key.items():
            selected_answer = detected_answers.get(question_number, "Blank/Unclear")
            if selected_answer == correct_answer:
                correct_count += 1
            elif selected_answer == "Blank/Unclear":
                blank_items.append(question_number)
            else:
                wrong_items.append((question_number, selected_answer, correct_answer))

        total_questions = len(answer_key)
        percentage = (correct_count / total_questions) * 100 if total_questions else 0
        result_lines = [
            f"Exam: {exam_name or 'Quizora Exam'}",
            f"Paper: {paper_num}",
            f"Total Questions: {total_questions}",
            f"Correct Answers: {correct_count}",
            f"Wrong Answers: {len(wrong_items)}",
            f"Blank/Unclear: {len(blank_items)}",
            f"Score: {percentage:.2f}%",
            "",
            "Detected Answers:",
        ]

        for question_number in sorted(answer_key, key=lambda item: int(item)):
            result_lines.append(
                f"Q{question_number}: {detected_answers.get(question_number, 'Blank/Unclear')} "
                f"(Correct: {answer_key[question_number]})"
            )

        if wrong_items:
            result_lines.extend(["", "Wrong Answer Details:"])
            for question_number, selected_answer, correct_answer in wrong_items:
                result_lines.append(f"Q{question_number}: selected {selected_answer}, correct {correct_answer}")

        self.latest_omr_result_text = "\n".join(result_lines)
        messagebox.showinfo("OMR Result", self.latest_omr_result_text)

    def save_omr_result(self) -> None:
        if not self.latest_omr_result_text:
            messagebox.showerror("Error", "No OMR result available to save.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Save OMR Result",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt")],
        )
        if not file_path:
            return

        with open(file_path, "w", encoding="utf-8") as result_file:
            result_file.write(self.latest_omr_result_text)

        messagebox.showinfo("Saved", "OMR result saved successfully.")

    def generate_ai_quiz(self) -> None:
        subject = self.ai_subject_entry.get().strip()
        num_questions = self.ai_num_questions_entry.get().strip()
        api_key = self.gemini_api_key or os.getenv("GEMINI_API_KEY")

        if not subject:
            messagebox.showerror("Error", "Please enter a subject.")
            return

        if not num_questions.isdigit() or int(num_questions) <= 0:
            messagebox.showerror("Error", "Please enter a valid number of questions.")
            return

        if not api_key:
            messagebox.showerror(
                "Missing API Key",
                "Please enter your Gemini API key or set GEMINI_API_KEY in your system.",
            )
            return

        self.ai_generate_button.configure(state="disabled")
        self.ai_status_label.configure(text="Generating quiz with AI. Please wait...")

        thread = threading.Thread(
            target=self._generate_ai_quiz_worker,
            args=(
                subject,
                int(num_questions),
                self.ai_difficulty_menu.get(),
                self.ai_topics_entry.get().strip(),
                self.ai_prompt_text.get("1.0", "end").strip(),
                "gemini-2.5-flash",
                api_key,
            ),
            daemon=True,
        )
        thread.start()

    def _generate_ai_quiz_worker(
        self,
        subject: str,
        num_questions: int,
        difficulty: str,
        focus_topics: str,
        user_prompt: str,
        model: str,
        api_key: str,
    ) -> None:
        try:
            prompt = self.build_quiz_prompt(
                subject=subject,
                num_questions=num_questions,
                difficulty=difficulty,
                focus_topics=focus_topics,
                user_prompt=user_prompt,
            )
            response_text = self.request_gemini_quiz(
                api_key=api_key,
                model=model,
                prompt=prompt,
            )
            payload = self.extract_json_payload(response_text)
            questions = self.parse_ai_questions(payload)
        except Exception as exc:
            self.root.after(0, lambda: self.on_ai_generation_error(str(exc)))
            return

        self.root.after(0, lambda: self.on_ai_generation_success(questions))

    def request_gemini_quiz(self, api_key: str, model: str, prompt: str) -> str:
        endpoint = (
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"{urllib.parse.quote(model)}:generateContent?key={urllib.parse.quote(api_key)}"
        )
        payload = {
            "contents": [
                {
                    "parts": [
                        {
                            "text": prompt,
                        }
                    ]
                }
            ]
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                raw_body = response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise ValueError(
                f"Gemini request failed with HTTP {exc.code}: {error_body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise ValueError(f"Could not reach Gemini API: {exc.reason}") from exc

        data = json.loads(raw_body)
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no candidates.")

        parts = candidates[0].get("content", {}).get("parts", [])
        text_chunks = [part.get("text", "") for part in parts if part.get("text")]
        if not text_chunks:
            raise ValueError("Gemini returned an empty response.")

        return "\n".join(text_chunks)

    def build_quiz_prompt(
        self,
        subject: str,
        num_questions: int,
        difficulty: str,
        focus_topics: str,
        user_prompt: str,
    ) -> str:
        topic_line = focus_topics if focus_topics else "Cover multiple important subtopics."
        return f"""
Generate a multiple-choice quiz as strict JSON only.

Requirements:
- Subject: {subject}
- Difficulty: {difficulty}
- Number of questions: {num_questions}
- Focus topics: {topic_line}
- Learning goal: {user_prompt}
- Each question must have exactly 4 options.
- Use practical, concept-checking questions.
- Spread questions across topics when possible.
- Return valid JSON with this shape:
{{
  "quiz_title": "string",
  "questions": [
    {{
      "question": "string",
      "topic": "string",
      "options": ["A", "B", "C", "D"],
      "answer_index": 0,
      "explanation": "short explanation"
    }}
  ]
}}
Do not include markdown fences.
""".strip()

    def extract_json_payload(self, response_text: str) -> dict:
        cleaned = response_text.strip()
        if cleaned.startswith("```"):
            lines = [line for line in cleaned.splitlines() if not line.strip().startswith("```")]
            cleaned = "\n".join(lines).strip()

        start_index = cleaned.find("{")
        end_index = cleaned.rfind("}")
        if start_index == -1 or end_index == -1:
            raise ValueError("AI response did not contain valid JSON.")

        return json.loads(cleaned[start_index : end_index + 1])

    def parse_ai_questions(self, payload: dict) -> list[AIQuizQuestion]:
        questions = []
        for item in payload.get("questions", []):
            options = item.get("options", [])
            answer_index = item.get("answer_index")
            if len(options) != 4 or not isinstance(answer_index, int) or answer_index not in range(4):
                raise ValueError("AI returned an invalid question format.")

            questions.append(
                AIQuizQuestion(
                    question=item.get("question", "").strip(),
                    options=options,
                    answer=answer_index,
                    topic=item.get("topic", "General").strip() or "General",
                    explanation=item.get("explanation", "No explanation provided.").strip(),
                )
            )

        if not questions:
            raise ValueError("AI did not return any questions.")

        return questions

    def on_ai_generation_error(self, error_message: str) -> None:
        self.ai_generate_button.configure(state="normal")
        self.ai_status_label.configure(text="Quiz generation failed.")
        messagebox.showerror("AI Quiz Error", f"Could not generate the quiz.\n\n{error_message}")

    def on_ai_generation_success(self, questions: list[AIQuizQuestion]) -> None:
        self.ai_questions = questions
        self.ai_answer_vars = [tk.StringVar(value="") for _ in questions]
        self.latest_report_text = ""
        self.ai_save_report_button.configure(state="disabled")

        self.ai_generate_button.configure(state="normal")
        self.ai_status_label.configure(text="Quiz generated successfully. Questions opened in a new window.")
        self.open_ai_quiz_window()

    def open_ai_quiz_window(self) -> None:
        if self.ai_quiz_window is not None and self.ai_quiz_window.winfo_exists():
            self.ai_quiz_window.destroy()

        self.ai_quiz_window = ctk.CTkToplevel(self.root)
        self.ai_quiz_window.title("AI Quiz")
        self.ai_quiz_window.geometry("900x700")
        self.ai_quiz_window.grid_columnconfigure(0, weight=1)
        self.ai_quiz_window.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self.ai_quiz_window,
            text=f"Generated Quiz: {len(self.ai_questions)} Questions",
            font=ctk.CTkFont(size=22, weight="bold"),
        ).grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        scroll_frame = ctk.CTkScrollableFrame(self.ai_quiz_window)
        scroll_frame.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="nsew")
        scroll_frame.grid_columnconfigure(0, weight=1)

        for index, question in enumerate(self.ai_questions):
            question_card = ctk.CTkFrame(scroll_frame)
            question_card.grid(row=index, column=0, padx=10, pady=8, sticky="ew")
            question_card.grid_columnconfigure(0, weight=1)

            ctk.CTkLabel(
                question_card,
                text=f"Q{index + 1}. {question.question}",
                wraplength=760,
                justify="left",
                anchor="w",
                font=ctk.CTkFont(size=15, weight="bold"),
            ).grid(row=0, column=0, padx=16, pady=(14, 6), sticky="w")

            ctk.CTkLabel(
                question_card,
                text=f"Topic: {question.topic}",
                font=ctk.CTkFont(size=12),
            ).grid(row=1, column=0, padx=16, pady=(0, 8), sticky="w")

            for option_index, option_text in enumerate(question.options):
                ctk.CTkRadioButton(
                    question_card,
                    text=f"{chr(65 + option_index)}. {option_text}",
                    variable=self.ai_answer_vars[index],
                    value=str(option_index),
                ).grid(row=option_index + 2, column=0, padx=16, pady=4, sticky="w")

        ctk.CTkButton(
            scroll_frame,
            text="Submit Quiz for Evaluation",
            command=self.evaluate_ai_quiz,
            fg_color="#1f6aa5",
            hover_color="#174f7a",
        ).grid(row=len(self.ai_questions), column=0, padx=10, pady=16, sticky="ew")

        self.ai_quiz_report_textbox = ctk.CTkTextbox(scroll_frame, height=260)
        self.ai_quiz_report_textbox.grid(
            row=len(self.ai_questions) + 1, column=0, padx=10, pady=(0, 12), sticky="ew"
        )
        self.ai_quiz_report_textbox.insert(
            "1.0",
            "Select your answers and click 'Submit Quiz for Evaluation' to view your report.",
        )
        self.ai_quiz_report_textbox.configure(state="disabled")
        self.ai_quiz_window.focus()

    def evaluate_ai_quiz(self) -> None:
        if not self.ai_questions:
            messagebox.showerror("Error", "No AI quiz available to evaluate.")
            return

        unanswered = [
            str(index + 1)
            for index, answer_var in enumerate(self.ai_answer_vars)
            if answer_var.get() == ""
        ]
        if unanswered:
            messagebox.showerror(
                "Incomplete Quiz",
                f"Please answer all questions before submitting.\nUnanswered: {', '.join(unanswered)}",
            )
            return

        correct_count = 0
        topic_totals = defaultdict(int)
        topic_correct = defaultdict(int)
        wrong_answers = []

        for index, question in enumerate(self.ai_questions):
            selected_index = int(self.ai_answer_vars[index].get())
            topic_totals[question.topic] += 1

            if selected_index == question.answer:
                correct_count += 1
                topic_correct[question.topic] += 1
                continue

            wrong_answers.append(
                {
                    "number": index + 1,
                    "question": question.question,
                    "topic": question.topic,
                    "selected": question.options[selected_index],
                    "correct": question.options[question.answer],
                    "explanation": question.explanation,
                }
            )

        total_questions = len(self.ai_questions)
        score_percent = (correct_count / total_questions) * 100

        weak_topics = []
        topic_lines = []
        for topic, total in sorted(topic_totals.items()):
            correct = topic_correct[topic]
            percent = (correct / total) * 100
            topic_lines.append(f"- {topic}: {correct}/{total} correct ({percent:.0f}%)")
            if percent < 60:
                weak_topics.append(topic)

        report_lines = [
            "AI QUIZ PERFORMANCE REPORT",
            "",
            f"Total Questions: {total_questions}",
            f"Correct Answers: {correct_count}",
            f"Score: {score_percent:.2f}%",
            "",
            "Topic-wise Performance:",
            *topic_lines,
            "",
            "Weak Topics To Improve:",
        ]

        if weak_topics:
            report_lines.extend(f"- {topic}" for topic in weak_topics)
        else:
            report_lines.append("- No major weak topics detected. Keep practicing mixed questions.")

        report_lines.extend(["", "Detailed Review:"])

        if wrong_answers:
            for item in wrong_answers:
                report_lines.extend(
                    [
                        f"- Q{item['number']} ({item['topic']}): {item['question']}",
                        f"  Your answer: {item['selected']}",
                        f"  Correct answer: {item['correct']}",
                        f"  Why: {item['explanation']}",
                        "",
                    ]
                )
        else:
            report_lines.append("- Excellent work. You answered every question correctly.")

        report_lines.extend(
            [
                "Improvement Suggestions:",
                self.build_improvement_suggestion(weak_topics, wrong_answers),
            ]
        )

        self.latest_report_text = "\n".join(report_lines).strip()
        if self.ai_quiz_report_textbox is not None and self.ai_quiz_report_textbox.winfo_exists():
            self.ai_quiz_report_textbox.configure(state="normal")
            self.ai_quiz_report_textbox.delete("1.0", "end")
            self.ai_quiz_report_textbox.insert("1.0", self.latest_report_text)
            self.ai_quiz_report_textbox.configure(state="disabled")

        self.ai_status_label.configure(text="Evaluation complete. Review your report below.")
        self.ai_save_report_button.configure(state="normal")

    def build_improvement_suggestion(self, weak_topics: list[str], wrong_answers: list[dict]) -> str:
        if weak_topics:
            focus_line = ", ".join(weak_topics)
            return (
                f"Spend your next study session on: {focus_line}. "
                "Revise the basic concepts first, then solve 5-10 questions per weak topic."
            )

        if wrong_answers:
            return (
                "You are close. Review the explanations for the missed questions and retry a fresh quiz "
                "on the same subject to strengthen consistency."
            )

        return (
            "Your performance is strong. Move to a higher difficulty level or try scenario-based questions "
            "to deepen understanding."
        )

    def save_report(self) -> None:
        if not self.latest_report_text:
            messagebox.showerror("Error", "No report available to save.")
            return

        file_path = filedialog.asksaveasfilename(
            title="Save Report",
            defaultextension=".txt",
            filetypes=[("Text Files", "*.txt")],
        )
        if not file_path:
            return

        with open(file_path, "w", encoding="utf-8") as report_file:
            report_file.write(self.latest_report_text)

        messagebox.showinfo("Saved", "Report saved successfully.")

    def run(self) -> None:
        self.root.mainloop()


if __name__ == "__main__":
    app = QuizNovaApp()
    app.run()
