from pypdf import PdfReader


def read_pdf(file_path):
    try:
        # Otwórz plik PDF
        with open(file_path, "rb") as file:
            reader = PdfReader(file)
            # Do przechowywania tekstu z całego dokumentu
            text = ""
            # Przechodzimy przez każdą stronę dokumentu i odczytujemy tekst
            for page in reader.pages:
                text += page.extract_text()
        return text
    except Exception as e:
        print(f"Wystąpił błąd podczas odczytu pliku PDF: {e}")
        return None


if __name__ == "__main__":
    document_path = "tmp/cv_2.pdf"
    pdf_text = read_pdf(document_path)
    if pdf_text:
        print(pdf_text)
