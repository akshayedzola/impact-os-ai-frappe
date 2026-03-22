import frappe
from frappe.model.document import Document
import re
import uuid


class IOSProject(Document):
    def before_insert(self):
        if not self.slug:
            self.slug = self._generate_slug()

    def before_save(self):
        if not self.slug:
            self.slug = self._generate_slug()

    def _generate_slug(self) -> str:
        """Generate a URL-safe slug from the project title."""
        if not self.project_title:
            return str(uuid.uuid4())[:8]

        base = self.project_title.lower().strip()
        base = re.sub(r"[^\w\s-]", "", base)
        base = re.sub(r"[\s_]+", "-", base)
        base = re.sub(r"-+", "-", base).strip("-")
        base = base[:50]

        slug = base
        counter = 1
        while frappe.db.exists("IOS Project", {"slug": slug}):
            slug = f"{base}-{counter}"
            counter += 1

        return slug
