"""Plain-English names for CIP fields of study.

The federal CIP taxonomy is precise and unreadable. "Registered Nursing, Nursing Administration,
Nursing Research and Clinical Nursing" is a correct label for CIP 51.38 and also a string no
member of the public has ever typed into a search box, and at 82 characters it is truncated in
search results. People search "nursing degree salary".

So we keep the official CIP description as provenance (shown on the page, used in the dataset,
never altered) and add a short human name for the fields that carry the traffic. Coverage is
deliberately partial: these are ranked by number of graduates, so a few dozen entries cover most
real searches, and anything unmapped falls back to a tidied version of the official label.

Rules for entries here:
  * Use the words a prospective student would say, not the taxonomy's.
  * Do not narrow the meaning. CIP 51.38 covers more than bedside nursing, so "Nursing" is fair
    but "Registered Nurse" would not be.
  * Never invent a distinction the data does not support.

Usage:
    from pipeline.cip_names import plain_name
    plain_name("5138", "Registered Nursing, ...")  -> "Nursing"
"""

from __future__ import annotations

# cip_code (4-digit, no dot) -> the name a person would use.
PLAIN: dict[str, str] = {
    # Health
    "5138": "Nursing",
    "5139": "Practical and Vocational Nursing",
    "5107": "Healthcare Administration",
    "5108": "Medical Assisting",
    "5109": "Allied Health Diagnostics and Treatment",
    "5100": "Health Sciences",
    "5102": "Speech-Language Pathology and Audiology",
    "5106": "Dental Assisting and Hygiene",
    "5115": "Mental Health and Counseling Services",
    "5112": "Medicine",
    "5120": "Pharmacy",
    "5122": "Public Health",
    "5123": "Physical and Occupational Therapy",
    "5110": "Medical Laboratory Science",
    "5135": "Massage Therapy and Bodywork",
    # Business
    "5202": "Business Administration",
    "5201": "Business",
    "5203": "Accounting",
    "5208": "Finance",
    "5214": "Marketing",
    "5210": "Human Resources",
    "5212": "Management Information Systems",
    "5213": "Management Science",
    "5209": "Hospitality Management",
    "5204": "Administrative and Office Support",
    # Computing and engineering
    "1101": "Computer and Information Science",
    "1107": "Computer Science",
    "1104": "Information Science",
    "1110": "IT Administration and Management",
    "1419": "Mechanical Engineering",
    "1410": "Electrical Engineering",
    "1408": "Civil Engineering",
    "1409": "Computer Engineering",
    "1407": "Chemical Engineering",
    "1405": "Biomedical Engineering",
    # Social sciences and humanities
    "4201": "Psychology",
    "4228": "Counseling Psychology",
    "4227": "Research Psychology",
    "4301": "Criminal Justice",
    "4510": "Political Science",
    "4511": "Sociology",
    "4506": "Economics",
    "4501": "Social Sciences",
    "4509": "International Relations",
    "4404": "Public Administration",
    "4407": "Social Work",
    "4504": "Criminology",
    "4400": "Human Services",
    "2301": "English",
    "5401": "History",
    "2201": "Law",
    "2701": "Mathematics",
    "2401": "Liberal Arts and General Studies",
    "3099": "Interdisciplinary Studies",
    "3906": "Theology and Ministry",
    "1907": "Human Development and Family Studies",
    # Sciences
    "2601": "Biology",
    "4005": "Chemistry",
    "3001": "Biological and Physical Sciences",
    "0301": "Natural Resources and Conservation",
    "2615": "Neuroscience",
    "2602": "Biochemistry and Molecular Biology",
    "4004": "Physics",
    "4008": "Physics",
    "4006": "Geology and Earth Science",
    # Education
    "1312": "Teacher Education (by level)",
    "1313": "Teacher Education (by subject)",
    "1304": "Educational Administration",
    "1310": "Special Education",
    "1301": "Education",
    "1303": "Curriculum and Instruction",
    "1311": "School Counseling",
    # Arts, media and communication
    "0901": "Communications and Media",
    "0909": "Public Relations and Advertising",
    "0904": "Journalism",
    "0907": "Radio, TV and Digital Media",
    "5004": "Design",
    "5007": "Fine Arts",
    "5009": "Music",
    "5006": "Film and Photography",
    "5005": "Theatre",
    # Trades and services
    "1204": "Cosmetology",
    "1205": "Culinary Arts",
    "4706": "Auto Repair Technology",
    "4702": "HVAC Technology",
    "4805": "Precision Metalworking",
    "4603": "Electrician Training",
    "4902": "Commercial Driving",
    "3105": "Kinesiology and Physical Education",
}


def tidy_official(official: str | None) -> str:
    """The official CIP label, minus the trailing period the federal file carries."""
    return (official or "").strip().rstrip(".").strip()


def plain_name(cip_code: str | None, official: str | None) -> str:
    """Short human name for a field, falling back to the tidied official label."""
    key = (cip_code or "").replace(".", "").strip()
    return PLAIN.get(key) or tidy_official(official)


def has_plain_name(cip_code: str | None) -> bool:
    """True when we have a curated name, i.e. the official label is worth showing separately."""
    return (cip_code or "").replace(".", "").strip() in PLAIN


def short_label(cip_code: str | None, official: str | None, limit: int = 42) -> str:
    """A title-length name. Curated where we have one, otherwise the leading clause.

    Many CIP labels are a head term followed by enumerated siblings, e.g. "Homeland Security, Law
    Enforcement, Firefighting and Related Protective Services, Other". The text before the first
    comma is both the head term and what people search, so for long labels we use it. We only do
    this when it leaves something substantial, and never for labels that are already short enough,
    so nothing is truncated into nonsense. The full official label still appears on the page.
    """
    name = plain_name(cip_code, official)
    if len(name) <= limit or has_plain_name(cip_code):
        return name
    head = name.split(",")[0].strip()
    return head if 8 <= len(head) < len(name) else name
