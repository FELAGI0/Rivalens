import enum


class PageKind(str, enum.Enum):
    PRICE = "price"
    LANDING = "landing"
    VACANCIES = "vacancies"
    NEWS = "news"
    REVIEWS = "reviews"
    OTHER = "other"


class UserPlan(str, enum.Enum):
    FREE = "free"
    PRO = "pro"
    BUSINESS = "business"
