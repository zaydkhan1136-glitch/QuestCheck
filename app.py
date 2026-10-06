from flask import Flask, render_template, request, redirect, url_for, send_file, flash
import sqlite3
import io
import re
from datetime import datetime

from PyPDF2 import PdfReader
from docx import Document

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

from sentence_transformers import SentenceTransformer

from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


app = Flask(__name__)
app.secret_key = "plagiarism-checker-secret"

DATABASE = "plagiarism_reports.db"


# ============================================================
# AI MODEL
# ============================================================

print("Loading AI semantic model...")

semantic_model = SentenceTransformer("all-MiniLM-L6-v2")

print("AI semantic model loaded successfully.")


# ============================================================
# DATABASE
# ============================================================

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():

    conn = get_db()

    conn.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment1_name TEXT,
            assignment2_name TEXT,
            combined_similarity REAL,
            tfidf_similarity REAL,
            semantic_similarity REAL,
            classification TEXT,
            created_at TEXT,
            assignment1_text TEXT,
            assignment2_text TEXT
        )
    """)

    # Safe migration for older databases.
    columns = {
        row["name"]
        for row in conn.execute("PRAGMA table_info(reports)").fetchall()
    }

    if "assignment1_text" not in columns:
        conn.execute("ALTER TABLE reports ADD COLUMN assignment1_text TEXT")

    if "assignment2_text" not in columns:
        conn.execute("ALTER TABLE reports ADD COLUMN assignment2_text TEXT")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS submissions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            assignment_name TEXT NOT NULL,
            student_name TEXT NOT NULL,
            submission_text TEXT NOT NULL,
            similarity_score REAL DEFAULT 0,
            classification TEXT DEFAULT 'Low',
            best_match_student TEXT,
            created_at TEXT
        )
    """)

    conn.commit()
    conn.close()


init_db()


# ============================================================
# FILE TEXT EXTRACTION
# ============================================================

def extract_file_text(file):

    if not file or not file.filename:
        return ""

    filename = file.filename.lower()

    try:

        if filename.endswith(".txt"):

            return file.read().decode(
                "utf-8",
                errors="ignore"
            )

        elif filename.endswith(".pdf"):

            reader = PdfReader(file)

            text = ""

            for page in reader.pages:

                page_text = page.extract_text()

                if page_text:
                    text += page_text + "\n"

            return text

        elif filename.endswith(".docx"):

            document = Document(file)

            return "\n".join(
                paragraph.text
                for paragraph in document.paragraphs
            )

    except Exception as e:

        print("File extraction error:", e)

    return ""


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):

    text = text or ""

    text = text.replace("\x00", " ")

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


# ============================================================
# TF-IDF
# ============================================================

def calculate_tfidf(text1, text2):

    try:

        vectorizer = TfidfVectorizer(
            stop_words="english"
        )

        vectors = vectorizer.fit_transform(
            [text1.lower(), text2.lower()]
        )

        score = cosine_similarity(
            vectors[0:1],
            vectors[1:2]
        )[0][0]

        return round(
            float(score * 100),
            2
        )

    except Exception as e:

        print("TF-IDF error:", e)

        return 0.0


# ============================================================
# AI SEMANTIC SIMILARITY
# ============================================================

def calculate_semantic(text1, text2):

    try:

        embeddings = semantic_model.encode(
            [text1, text2],
            normalize_embeddings=True
        )

        score = cosine_similarity(
            [embeddings[0]],
            [embeddings[1]]
        )[0][0]

        return round(
            float(score * 100),
            2
        )

    except Exception as e:

        print("Semantic error:", e)

        return 0.0


# ============================================================
# SENTENCES
# ============================================================

def split_sentences(text):

    sentences = re.split(
        r"(?<=[.!?])\s+|\n+",
        text
    )

    result = []

    for sentence in sentences:

        sentence = sentence.strip()

        if not sentence:
            continue

        # Remove table/PDF noise
        words = re.findall(
            r"[A-Za-z]{2,}",
            sentence
        )

        # Ignore tiny fragments such as:
        # "95 cgpa 4"
        # "95 g cm3"
        if len(words) < 5:
            continue

        result.append(sentence)

    return result


# ============================================================
# HIGHLIGHT COMMON WORDS
# ============================================================

STOP_WORDS = {
    "the", "and", "that", "this", "with",
    "from", "have", "has", "been", "were",
    "they", "their", "there", "which",
    "about", "into", "also", "such",
    "than", "then", "when", "where",
    "what", "will", "would", "could",
    "should", "using", "used", "are",
    "for", "was", "but", "not", "you",
    "your", "our", "its", "can"
}


def highlight_words(sentence1, sentence2):

    words1 = set(
        re.findall(
            r"\b[A-Za-z]{3,}\b",
            sentence1.lower()
        )
    )

    words2 = set(
        re.findall(
            r"\b[A-Za-z]{3,}\b",
            sentence2.lower()
        )
    )

    common = (
        words1.intersection(words2)
        - STOP_WORDS
    )

    def highlight(sentence):

        def replace(match):

            word = match.group(0)

            if word.lower() in common:

                return f"<mark>{word}</mark>"

            return word

        return re.sub(
            r"\b[A-Za-z]{3,}\b",
            replace,
            sentence
        )

    return (
        highlight(sentence1),
        highlight(sentence2)
    )


# ============================================================
# FIND MEANINGFUL MATCHES
# ============================================================

def find_semantic_matches(text1, text2):

    sentences1 = split_sentences(text1)
    sentences2 = split_sentences(text2)

    if not sentences1 or not sentences2:
        return []

    try:

        embeddings1 = semantic_model.encode(
            sentences1,
            normalize_embeddings=True
        )

        embeddings2 = semantic_model.encode(
            sentences2,
            normalize_embeddings=True
        )

        matrix = cosine_similarity(
            embeddings1,
            embeddings2
        )

        matches = []

        for i, sentence1 in enumerate(sentences1):

            best_index = matrix[i].argmax()

            score = float(
                matrix[i][best_index] * 100
            )

            sentence2 = sentences2[best_index]

            words1 = re.findall(
                r"[A-Za-z]{2,}",
                sentence1
            )

            words2 = re.findall(
                r"[A-Za-z]{2,}",
                sentence2
            )

            # Don't report tiny fragments.
            if len(words1) < 5 or len(words2) < 5:
                continue

            # Meaningful threshold.
            if score < 55:
                continue

            highlighted1, highlighted2 = (
                highlight_words(
                    sentence1,
                    sentence2
                )
            )

            matches.append({
                "sentence1": sentence1,
                "sentence2": sentence2,
                "score": round(score, 2),
                "highlighted1": highlighted1,
                "highlighted2": highlighted2
            })

        matches.sort(
            key=lambda x: x["score"],
            reverse=True
        )

        return matches[:20]

    except Exception as e:

        print("Sentence matching error:", e)

        return []


# ============================================================
# STUDENT WRITING ANALYSIS
# ============================================================

def analyze_writing(text):
    text = clean_text(text)
    words = re.findall(r"\b[A-Za-z]+(?:['-][A-Za-z]+)*\b", text)
    sentences = split_sentences(text)
    word_count = len(words)
    sentence_count = len(sentences)
    character_count = len(re.sub(r"\s", "", text))
    average_sentence_length = round(word_count / sentence_count, 1) if sentence_count else 0

    if word_count == 0:
        readability = "No text"
    elif average_sentence_length <= 18:
        readability = "Easy to read"
    elif average_sentence_length <= 25:
        readability = "Moderate"
    else:
        readability = "Complex"

    return {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "character_count": character_count,
        "average_sentence_length": average_sentence_length,
        "readability": readability
    }


def citation_analysis(text):
    patterns = [
        r"\([A-Z][A-Za-z]+,\s*\d{4}\)",
        r"\[[0-9]+\]",
        r"\bdoi\s*:",
        r"\bhttps?://",
        r"\breferences\b",
        r"\bbibliography\b",
        r"\bworks cited\b"
    ]

    found = sum(
        bool(re.search(pattern, text or "", flags=re.IGNORECASE))
        for pattern in patterns
    )

    return {
        "has_citations": found > 0,
        "citation_indicator_count": found
    }


def writing_suggestions(analysis):
    suggestions = []

    if analysis["word_count"] < 150:
        suggestions.append(
            "Consider adding more explanation or supporting evidence if required."
        )

    if analysis["average_sentence_length"] > 25:
        suggestions.append(
            "Some sentences are long. Consider splitting them into shorter sentences."
        )

    if analysis["average_sentence_length"] and analysis["average_sentence_length"] < 7:
        suggestions.append(
            "Your sentences are quite short. Connect related ideas where appropriate."
        )

    if not suggestions:
        suggestions.append(
            "Writing statistics look reasonable. Review grammar, evidence and citations before submission."
        )

    return suggestions


# ============================================================
# CLASSIFICATION
# ============================================================

def classify(score):

    if score >= 70:
        return "High"

    if score >= 40:
        return "Moderate"

    return "Low"


# ============================================================
# DASHBOARD
# ============================================================

def dashboard_data():

    conn = get_db()

    reports = conn.execute(
        """
        SELECT *
        FROM reports
        ORDER BY id DESC
        """
    ).fetchall()

    conn.close()

    total = len(reports)

    high = sum(
        r["classification"] == "High"
        for r in reports
    )

    moderate = sum(
        r["classification"] == "Moderate"
        for r in reports
    )

    low = sum(
        r["classification"] == "Low"
        for r in reports
    )

    average = 0

    if total:

        average = round(
            sum(
                r["combined_similarity"]
                for r in reports
            ) / total,
            2
        )

    return (
        reports,
        total,
        high,
        moderate,
        low,
        average
    )


# ============================================================
# HOME
# ============================================================

@app.route("/")
def index():

    (
        reports,
        total,
        high,
        moderate,
        low,
        average
    ) = dashboard_data()

    return render_template(
        "index.html",
        reports=reports,
        total=total,
        high=high,
        moderate=moderate,
        low=low,
        average=average,
        latest=None,
        combined_similarity=0,
        tfidf_similarity=0,
        semantic_similarity=0,
        semantic_matches=[],
        assignment1_name="",
        assignment2_name="",
        writing_analysis1=analyze_writing(""),
        writing_analysis2=analyze_writing(""),
        citation_analysis1=citation_analysis(""),
        citation_analysis2=citation_analysis(""),
        writing_suggestions=[]
    )


# ============================================================
# CHECK PLAGIARISM
# ============================================================

@app.route("/check", methods=["POST"])
def check_plagiarism():

    print("\n================================")
    print("NEW PLAGIARISM CHECK")
    print("================================")

    # Text entered by user
    text1 = request.form.get(
        "assignment1_text",
        ""
    ).strip()

    text2 = request.form.get(
        "assignment2_text",
        ""
    ).strip()

    # Optional uploaded files
    file1 = request.files.get("assignment1_file")
    file2 = request.files.get("assignment2_file")

    # If text box is empty, try file
    if not text1 and file1 and file1.filename:

        text1 = extract_file_text(file1)

    if not text2 and file2 and file2.filename:

        text2 = extract_file_text(file2)

    text1 = clean_text(text1)
    text2 = clean_text(text2)

    # Names
    name1 = "Pasted Assignment 1"
    name2 = "Pasted Assignment 2"

    if file1 and file1.filename:
        name1 = file1.filename

    if file2 and file2.filename:
        name2 = file2.filename

    if not text1 or not text2:

        flash(
            "Please enter both assignments or upload both files.",
            "error"
        )

        return redirect(
            url_for("index")
        )

    print(
        "Assignment 1 characters:",
        len(text1)
    )

    print(
        "Assignment 2 characters:",
        len(text2)
    )

    # Calculate scores
    tfidf = calculate_tfidf(
        text1,
        text2
    )

    semantic = calculate_semantic(
        text1,
        text2
    )

    combined = round(
        (
            tfidf * 0.40
        )
        +
        (
            semantic * 0.60
        ),
        2
    )

    classification = classify(
        combined
    )

    matches = find_semantic_matches(
        text1,
        text2
    )

    print("TF-IDF:", tfidf)
    print("AI Semantic:", semantic)
    print("Combined:", combined)
    print("Classification:", classification)
    print("Meaningful matches:", len(matches))

    # Save report
    conn = get_db()

    conn.execute(
        """
        INSERT INTO reports (
            assignment1_name,
            assignment2_name,
            combined_similarity,
            tfidf_similarity,
            semantic_similarity,
            classification,
            created_at,
            assignment1_text,
            assignment2_text
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            name1,
            name2,
            combined,
            tfidf,
            semantic,
            classification,
            datetime.now().strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
            text1,
            text2
        )
    )

    conn.commit()
    conn.close()

    (
        reports,
        total,
        high,
        moderate,
        low,
        average
    ) = dashboard_data()

    return render_template(
        "index.html",

        reports=reports,

        total=total,

        high=high,

        moderate=moderate,

        low=low,

        average=average,

        latest=reports[0],

        combined_similarity=combined,

        tfidf_similarity=tfidf,

        semantic_similarity=semantic,

        semantic_matches=matches,

        assignment1_name=name1,

        assignment2_name=name2,

        writing_analysis1=analyze_writing(text1),

        writing_analysis2=analyze_writing(text2),

        citation_analysis1=citation_analysis(text1),

        citation_analysis2=citation_analysis(text2),

        writing_suggestions=writing_suggestions(
            analyze_writing(text1)
        )
    )


# ============================================================
# STUDENT WRITING ANALYSIS API
# ============================================================

@app.route("/analyze-writing", methods=["POST"])
def analyze_writing_route():

    text = request.form.get("text", "").strip()

    if not text:
        return {
            "success": False,
            "message": "Please enter some text."
        }, 400

    analysis = analyze_writing(text)
    citations = citation_analysis(text)

    return {
        "success": True,
        "analysis": analysis,
        "citations": citations,
        "suggestions": writing_suggestions(analysis)
    }


# ============================================================
# DOWNLOAD PDF
# ============================================================

@app.route("/download/<int:report_id>")
def download_report(report_id):

    conn = get_db()
    report = conn.execute(
        "SELECT * FROM reports WHERE id = ?",
        (report_id,)
    ).fetchone()
    conn.close()

    if not report:
        return "Report not found", 404

    text1 = report["assignment1_text"] or ""
    text2 = report["assignment2_text"] or ""

    matches = find_semantic_matches(text1, text2)
    analysis1 = analyze_writing(text1)
    analysis2 = analyze_writing(text2)
    citations1 = citation_analysis(text1)
    citations2 = citation_analysis(text2)

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title = styles["Title"]
    heading = styles["Heading2"]
    normal = styles["BodyText"]

    story = []

    story.append(Paragraph("QUESTCHECK", title))
    story.append(Paragraph("Detailed AI Assignment Plagiarism Report", heading))
    story.append(Spacer(1, 14))

    story.append(Paragraph(
        f"<b>Assignment 1:</b> {report['assignment1_name']}", normal))
    story.append(Paragraph(
        f"<b>Assignment 2:</b> {report['assignment2_name']}", normal))
    story.append(Paragraph(
        f"<b>Generated:</b> {report['created_at']}", normal))
    story.append(Spacer(1, 14))

    story.append(Paragraph("1. Overall Result", heading))
    story.append(Paragraph(
        f"<b>Overall similarity:</b> {report['combined_similarity']}%", normal))
    story.append(Paragraph(
        f"<b>Risk classification:</b> {report['classification']}", normal))
    story.append(Paragraph(
        "High: 70% or above | Moderate: 40%-69.99% | Low: below 40%",
        normal))
    story.append(Spacer(1, 12))

    story.append(Paragraph("2. Similarity Breakdown", heading))
    story.append(Paragraph(
        f"<b>TF-IDF similarity:</b> {report['tfidf_similarity']}% "
        "(lexical/word-pattern similarity)", normal))
    story.append(Paragraph(
        f"<b>AI semantic similarity:</b> {report['semantic_similarity']}% "
        "(meaning/context similarity)", normal))
    story.append(Paragraph(
        "<b>Final score:</b> 40% TF-IDF + 60% AI semantic similarity.",
        normal))
    story.append(Spacer(1, 12))

    story.append(Paragraph("3. Assignment Statistics", heading))
    story.append(Paragraph(
        f"<b>Assignment 1:</b> {analysis1['word_count']} words, "
        f"{analysis1['sentence_count']} sentences, "
        f"average sentence length {analysis1['average_sentence_length']} words, "
        f"readability: {analysis1['readability']}.", normal))
    story.append(Paragraph(
        f"<b>Assignment 2:</b> {analysis2['word_count']} words, "
        f"{analysis2['sentence_count']} sentences, "
        f"average sentence length {analysis2['average_sentence_length']} words, "
        f"readability: {analysis2['readability']}.", normal))
    story.append(Spacer(1, 12))

    story.append(Paragraph("4. Citation Analysis", heading))
    story.append(Paragraph(
        f"Assignment 1 citations/references indicators: "
        f"{'Detected' if citations1['has_citations'] else 'Not detected'}.", normal))
    story.append(Paragraph(
        f"Assignment 2 citations/references indicators: "
        f"{'Detected' if citations2['has_citations'] else 'Not detected'}.", normal))
    story.append(Spacer(1, 12))

    story.append(Paragraph("5. Matching Passages", heading))

    if matches:
        for i, match in enumerate(matches[:10], 1):
            story.append(Paragraph(
                f"<b>Match {i} — {match['score']}%</b>", normal))
            story.append(Paragraph(
                f"<b>Assignment 1:</b> {match['sentence1']}", normal))
            story.append(Paragraph(
                f"<b>Assignment 2:</b> {match['sentence2']}", normal))
            story.append(Spacer(1, 8))
    else:
        story.append(Paragraph(
            "No strong sentence-level semantic matches were detected.",
            normal))

    story.append(Spacer(1, 10))
    story.append(Paragraph("6. Interpretation", heading))

    if report["classification"] == "High":
        interpretation = (
            "The system found a high level of similarity. The teacher should "
            "review the highlighted/matching passages and source context before "
            "making an academic-integrity decision."
        )
    elif report["classification"] == "Moderate":
        interpretation = (
            "The system found moderate similarity. Some shared wording or "
            "ideas may be legitimate, but the matching passages should be reviewed."
        )
    else:
        interpretation = (
            "The system found low similarity. This does not guarantee that "
            "the assignments are completely independent."
        )

    story.append(Paragraph(interpretation, normal))
    story.append(Spacer(1, 12))

    story.append(Paragraph("7. Student Pre-Submission Checklist", heading))
    for item in [
        "Review matching passages and confirm sources are properly acknowledged.",
        "Check citations and references.",
        "Rewrite ideas in your own words where appropriate.",
        "Review grammar, structure and supporting evidence.",
        "Follow your institution's academic-integrity rules."
    ]:
        story.append(Paragraph("• " + item, normal))

    story.append(Spacer(1, 12))
    story.append(Paragraph("8. Methodology and Disclaimer", heading))
    story.append(Paragraph(
        "QuestCheck combines TF-IDF lexical similarity with Sentence-Transformer "
        "semantic similarity. A similarity score is an indicator, not proof of "
        "plagiarism. Human review and source verification are required for final "
        "academic decisions.",
        normal))

    doc.build(story)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=f"QuestCheck_Detailed_Report_{report_id}.pdf",
        mimetype="application/pdf"
    )


# ============================================================
# DELETE ONE REPORT
# ============================================================

@app.route("/delete/<int:report_id>")
def delete_report(report_id):

    conn = get_db()

    conn.execute(
        "DELETE FROM reports WHERE id = ?",
        (report_id,)
    )

    conn.commit()
    conn.close()

    return redirect(
        url_for("index")
    )


# ============================================================
# DELETE ALL
# ============================================================

@app.route("/delete-all")
def delete_all_reports():

    conn = get_db()

    conn.execute(
        "DELETE FROM reports"
    )

    conn.commit()
    conn.close()

    return redirect(
        url_for("index")
    )

# ============================================================
# TEACHER DASHBOARD
# ============================================================

def teacher_dashboard_data():
    conn = get_db()

    submissions = conn.execute(
        "SELECT * FROM submissions ORDER BY id DESC"
    ).fetchall()

    conn.close()

    total = len(submissions)
    students = len(set(s["student_name"] for s in submissions))
    assignments = len(set(s["assignment_name"] for s in submissions))
    high = sum(s["classification"] == "High" for s in submissions)
    moderate = sum(s["classification"] == "Moderate" for s in submissions)
    low = sum(s["classification"] == "Low" for s in submissions)

    average = round(
        sum(float(s["similarity_score"] or 0) for s in submissions) / total,
        2
    ) if total else 0

    return {
        "submissions": submissions,
        "teacher_total": total,
        "teacher_students": students,
        "teacher_assignments": assignments,
        "teacher_high": high,
        "teacher_moderate": moderate,
        "teacher_low": low,
        "teacher_average": average
    }


def compare_submission_to_others(submission_id):
    conn = get_db()

    submission = conn.execute(
        "SELECT * FROM submissions WHERE id = ?",
        (submission_id,)
    ).fetchone()

    if not submission:
        conn.close()
        return None, []

    others = conn.execute(
        """
        SELECT * FROM submissions
        WHERE assignment_name = ? AND id != ?
        """,
        (submission["assignment_name"], submission_id)
    ).fetchall()

    conn.close()

    comparisons = []

    for other in others:
        tfidf = calculate_tfidf(
            submission["submission_text"],
            other["submission_text"]
        )
        semantic = calculate_semantic(
            submission["submission_text"],
            other["submission_text"]
        )
        score = round(tfidf * 0.40 + semantic * 0.60, 2)

        comparisons.append({
            "student_name": other["student_name"],
            "tfidf": tfidf,
            "semantic": semantic,
            "score": score,
            "classification": classify(score)
        })

    comparisons.sort(key=lambda x: x["score"], reverse=True)
    return submission, comparisons


@app.route("/teacher")
def teacher_dashboard():
    return render_template(
        "teacher.html",
        **teacher_dashboard_data(),
        selected_submission=None,
        comparisons=[]
    )


@app.route("/teacher/submit", methods=["POST"])
def teacher_submit():
    assignment_name = request.form.get("assignment_name", "").strip()
    student_name = request.form.get("student_name", "").strip()
    text = request.form.get("submission_text", "").strip()
    uploaded = request.files.get("submission_file")

    if not text and uploaded and uploaded.filename:
        text = extract_file_text(uploaded)

    text = clean_text(text)

    if not assignment_name or not student_name or not text:
        flash("Assignment name, student name and submission are required.", "error")
        return redirect(url_for("teacher_dashboard"))

    conn = get_db()

    existing = conn.execute(
        "SELECT * FROM submissions WHERE assignment_name = ?",
        (assignment_name,)
    ).fetchall()

    best_score = 0.0
    best_student = ""

    for other in existing:
        tfidf = calculate_tfidf(text, other["submission_text"])
        semantic = calculate_semantic(text, other["submission_text"])
        score = round(tfidf * 0.40 + semantic * 0.60, 2)

        if score > best_score:
            best_score = score
            best_student = other["student_name"]

    conn.execute(
        """
        INSERT INTO submissions (
            assignment_name,
            student_name,
            submission_text,
            similarity_score,
            classification,
            best_match_student,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            assignment_name,
            student_name,
            text,
            best_score,
            classify(best_score),
            best_student,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        )
    )

    conn.commit()

    # Recalculate every submission in this assignment.
    rows = conn.execute(
        "SELECT * FROM submissions WHERE assignment_name = ?",
        (assignment_name,)
    ).fetchall()

    for row in rows:
        highest = 0.0
        match_student = ""

        for other in rows:
            if row["id"] == other["id"]:
                continue

            tfidf = calculate_tfidf(
                row["submission_text"],
                other["submission_text"]
            )
            semantic = calculate_semantic(
                row["submission_text"],
                other["submission_text"]
            )
            score = round(tfidf * 0.40 + semantic * 0.60, 2)

            if score > highest:
                highest = score
                match_student = other["student_name"]

        conn.execute(
            """
            UPDATE submissions
            SET similarity_score = ?,
                classification = ?,
                best_match_student = ?
            WHERE id = ?
            """,
            (
                highest,
                classify(highest),
                match_student,
                row["id"]
            )
        )

    conn.commit()
    conn.close()

    return redirect(url_for("teacher_dashboard"))


@app.route("/teacher/compare/<int:submission_id>")
def teacher_compare(submission_id):
    submission, comparisons = compare_submission_to_others(submission_id)

    if not submission:
        return redirect(url_for("teacher_dashboard"))

    return render_template(
        "teacher.html",
        **teacher_dashboard_data(),
        selected_submission=submission,
        comparisons=comparisons
    )


@app.route("/teacher/delete/<int:submission_id>", methods=["POST"])
def teacher_delete(submission_id):
    conn = get_db()
    conn.execute(
        "DELETE FROM submissions WHERE id = ?",
        (submission_id,)
    )
    conn.commit()
    conn.close()
    return redirect(url_for("teacher_dashboard"))


@app.route("/teacher/delete-all", methods=["POST"])
def teacher_delete_all():
    conn = get_db()
    conn.execute("DELETE FROM submissions")
    conn.commit()
    conn.close()
    return redirect(url_for("teacher_dashboard"))


@app.route("/teacher/download/<int:submission_id>")
def teacher_download_report(submission_id):
    submission, comparisons = compare_submission_to_others(submission_id)

    if not submission:
        return "Submission not found", 404

    buffer = io.BytesIO()

    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    title = styles["Title"]
    heading = styles["Heading2"]
    normal = styles["BodyText"]

    story = []

    story.append(Paragraph("QUESTCHECK", title))
    story.append(Paragraph("Detailed Teacher Plagiarism Report", heading))
    story.append(Spacer(1, 14))

    story.append(Paragraph(
        f"<b>Assignment:</b> {submission['assignment_name']}", normal))
    story.append(Paragraph(
        f"<b>Student:</b> {submission['student_name']}", normal))
    story.append(Paragraph(
        f"<b>Submission date:</b> {submission['created_at']}", normal))
    story.append(Spacer(1, 14))

    story.append(Paragraph("1. Overall Student Risk", heading))
    story.append(Paragraph(
        f"<b>Highest similarity:</b> {submission['similarity_score']}%", normal))
    story.append(Paragraph(
        f"<b>Classification:</b> {submission['classification']}", normal))
    story.append(Paragraph(
        f"<b>Best matching student:</b> "
        f"{submission['best_match_student'] or 'None'}", normal))
    story.append(Spacer(1, 12))

    story.append(Paragraph("2. Comparison With Other Students", heading))

    if comparisons:
        for i, item in enumerate(comparisons[:15], 1):
            story.append(Paragraph(
                f"<b>{i}. {item['student_name']}</b> — "
                f"{item['score']}% ({item['classification']})", normal))
            story.append(Paragraph(
                f"TF-IDF: {item['tfidf']}% | "
                f"AI Semantic: {item['semantic']}%", normal))
            story.append(Spacer(1, 7))
    else:
        story.append(Paragraph(
            "No other submission exists for this assignment.", normal))

    story.append(Spacer(1, 12))
    story.append(Paragraph("3. Interpretation", heading))

    if submission["classification"] == "High":
        text = (
            "The submission has high similarity with another student submission. "
            "Review the original submissions, matching passages and legitimate "
            "shared sources before reaching an academic-integrity conclusion."
        )
    elif submission["classification"] == "Moderate":
        text = (
            "The submission has moderate similarity. Additional review is "
            "recommended, especially for the highest matching student."
        )
    else:
        text = (
            "The submission has low similarity against the other stored "
            "submissions for this assignment."
        )

    story.append(Paragraph(text, normal))
    story.append(Spacer(1, 12))

    story.append(Paragraph("4. Methodology", heading))
    story.append(Paragraph(
        "Each student submission is compared with other submissions for the "
        "same assignment. The final score uses 40% TF-IDF similarity and "
        "60% AI semantic similarity. The score is an indicator and should "
        "not be treated as automatic proof of plagiarism.",
        normal))

    doc.build(story)
    buffer.seek(0)

    return send_file(
        buffer,
        as_attachment=True,
        download_name=(
            f"QuestCheck_Teacher_Report_{submission_id}.pdf"
        ),
        mimetype="application/pdf"
    )


# ============================================================
# RUN
# ============================================================

if __name__ == "__main__":

    app.run(
        debug=True
    )