"""Create the synthetic practice PDF shipped with the local preview."""

from pathlib import Path

from reportlab.lib.colors import HexColor
from reportlab.pdfgen.canvas import Canvas


def make_sample(path):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    c = Canvas(str(path), pagesize=(612, 792))
    for n, title in enumerate(["Make it yours.", "Put pages in order.", "Keep the original."]):
        c.setFillColor(HexColor("#16232f"))
        c.rect(0, 622, 612, 170, fill=1, stroke=0)
        c.setFillColor(HexColor("#a9edcc"))
        c.setFont("Helvetica-Bold", 11)
        c.drawString(48, 742, "FORGE PDF  /  PRACTICE DOCUMENT")
        c.setFillColorRGB(1, 1, 1)
        c.setFont("Helvetica-Bold", 34)
        c.drawString(48, 678, title)
        c.setFillColor(HexColor("#203340"))
        c.setFont("Helvetica", 13)
        lines = [
            "A simple place to try your new desktop editor.",
            "No private information. No account. Just a few useful edits.",
            "",
            "01   Choose Whiteout and drag over the sample line below.",
            "02   Choose Add text, type a replacement, and click to place it.",
            "03   Highlight a sentence, then try Undo and Redo.",
        ]
        for line_number, line in enumerate(lines):
            c.drawString(48, 570 - 27 * line_number, line)
        c.setFillColor(HexColor("#eff3f5"))
        c.roundRect(48, 268, 516, 90, 8, fill=1, stroke=0)
        c.setFillColor(HexColor("#203340"))
        c.setFont("Helvetica-Bold", 20)
        c.drawString(68, 310, "Cover this line and write something better.")
        c.setFont("Helvetica", 11)
        c.drawString(48, 210, "Whiteout is visual cover, not secure redaction.")
        c.drawString(48, 190, "Covered text remains in the PDF and can still be extracted.")
        c.setStrokeColor(HexColor("#d5dee3"))
        c.line(48, 94, 564, 94)
        c.setFont("Helvetica", 10)
        c.drawString(48, 70, "Synthetic sample / Save an edited copy under a new name")
        c.drawRightString(564, 70, f"{n + 1} / 3")
        c.showPage()
    c.save()


if __name__ == "__main__":
    make_sample(Path(__file__).resolve().parents[1] / "examples" / "Welcome.pdf")
