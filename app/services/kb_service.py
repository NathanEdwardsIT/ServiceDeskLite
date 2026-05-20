import re
from difflib import SequenceMatcher

from sqlalchemy.orm import Session

from app.models.entities import KBArticle, Ticket


class KnowledgeBaseService:
    def __init__(self, db: Session):
        self.db = db

    def search(self, query: str, limit: int = 10) -> list[KBArticle]:
        pattern = f"%{query}%"
        return (
            self.db.query(KBArticle)
            .filter(
                KBArticle.is_published.is_(True),
                (KBArticle.title.ilike(pattern))
                | (KBArticle.content.ilike(pattern))
                | (KBArticle.tags.ilike(pattern)),
            )
            .order_by(KBArticle.helpful_count.desc())
            .limit(limit)
            .all()
        )

    def suggest_for_ticket(self, title: str, description: str, limit: int = 5) -> list[tuple[KBArticle, float]]:
        articles = self.db.query(KBArticle).filter(KBArticle.is_published.is_(True)).all()
        combined = f"{title} {description}".lower()
        results = []
        for article in articles:
            corpus = f"{article.title} {article.content} {article.tags or ''}".lower()
            score = SequenceMatcher(None, combined, corpus).ratio()
            if score > 0.35:
                results.append((article, round(score, 3)))
        results.sort(key=lambda x: x[1], reverse=True)
        return results[:limit]

    def link_to_ticket(self, ticket: Ticket, article_id: int) -> KBArticle | None:
        article = self.db.query(KBArticle).filter(KBArticle.id == article_id).first()
        if article:
            ticket.kb_article_id = article.id
            article.view_count += 1
            self.db.flush()
        return article

    def slugify(self, title: str) -> str:
        slug = re.sub(r"[^\w\s-]", "", title.lower())
        slug = re.sub(r"[\s_-]+", "-", slug).strip("-")
        return slug[:120]
