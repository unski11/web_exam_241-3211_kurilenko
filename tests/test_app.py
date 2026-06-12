import io

import pytest

from app import Book, Review, ReviewStatus, create_app, db


@pytest.fixture()
def app():
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "WTF_CSRF_ENABLED": False,
        }
    )
    yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def login(client, username, password):
    return client.post("/login", data={"login": username, "password": password}, follow_redirects=True)


def test_public_pages_and_auth_redirect(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Пикник на обочине".encode() in response.data

    response = client.get("/books/new", follow_redirects=True)
    assert "Для выполнения данного действия необходимо пройти процедуру аутентификации".encode() in response.data


def test_user_can_create_pending_review_and_see_my_reviews(client, app):
    with app.app_context():
        book = Book(title="Новая книга", short_description="Описание", year=2020, publisher="Тест", author="Автор", page_count=10)
        book.genres = []
        db.session.add(book)
        db.session.commit()
        book_id = book.id

    login(client, "admin", "admin")
    client.get("/logout")
    login(client, "user", "user")
    response = client.post(
        f"/books/{book_id}/reviews/new",
        data={"rating": "5", "text": "**Отлично**"},
        follow_redirects=True,
    )
    assert "Рецензия отправлена на рассмотрение".encode() in response.data

    with app.app_context():
        review = Review.query.filter_by(book_id=book_id).one()
        assert review.status.name == "на рассмотрении"

    response = client.get("/my-reviews")
    assert "на рассмотрении".encode() in response.data


def test_moderator_approves_review(client, app):
    login(client, "moderator", "moderator")
    with app.app_context():
        review = Review.query.join(ReviewStatus).filter(ReviewStatus.name == "на рассмотрении").first()
        review_id = review.id

    response = client.post(
        f"/moderation/reviews/{review_id}",
        data={"action": "approve"},
        follow_redirects=True,
    )
    assert "Рецензия одобрена".encode() in response.data

    with app.app_context():
        assert db.session.get(Review, review_id).status.name == "одобрена"


def test_admin_can_create_and_delete_book(client, app):
    login(client, "admin", "admin")
    image = io.BytesIO(b"fake image data")
    response = client.post(
        "/books/new",
        data={
            "title": "Тестовая книга",
            "short_description": "Описание <script>alert(1)</script>",
            "year": "2024",
            "publisher": "Издательство",
            "author": "Автор",
            "page_count": "100",
            "genres": ["1"],
            "cover": (image, "cover.jpg"),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert "Данные книги успешно сохранены".encode() in response.data

    with app.app_context():
        book = Book.query.filter_by(title="Тестовая книга").one()
        assert "<script>" not in book.short_description
        book_id = book.id

    response = client.post(f"/books/{book_id}/delete", follow_redirects=True)
    assert "успешно удалена".encode() in response.data
