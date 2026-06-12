from datetime import datetime
from pathlib import Path

import bleach
import markdown
from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_from_directory,
    url_for,
)
from flask_login import (
    LoginManager,
    UserMixin,
    current_user,
    login_required,
    login_user,
    logout_user,
)
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import func
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = Path(__file__).resolve().parent
UPLOAD_DIR = BASE_DIR / "uploads" / "covers"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}

db = SQLAlchemy()
login_manager = LoginManager()
login_manager.login_view = "login"
login_manager.login_message = "Для выполнения данного действия необходимо пройти процедуру аутентификации"
login_manager.login_message_category = "warning"

book_genres = db.Table(
    "book_genres",
    db.Column("book_id", db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), primary_key=True),
    db.Column("genre_id", db.Integer, db.ForeignKey("genres.id", ondelete="CASCADE"), primary_key=True),
)


class Role(db.Model):
    __tablename__ = "roles"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)
    description = db.Column(db.Text, nullable=False)
    users = db.relationship("User", back_populates="role")


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    login = db.Column(db.String(80), nullable=False, unique=True)
    password_hash = db.Column(db.String(255), nullable=False)
    last_name = db.Column(db.String(120), nullable=False)
    first_name = db.Column(db.String(120), nullable=False)
    middle_name = db.Column(db.String(120))
    role_id = db.Column(db.Integer, db.ForeignKey("roles.id"), nullable=False)

    role = db.relationship("Role", back_populates="users")
    reviews = db.relationship("Review", back_populates="user", cascade="all, delete-orphan")

    @property
    def full_name(self):
        parts = [self.last_name, self.first_name, self.middle_name]
        return " ".join(part for part in parts if part)

    def has_role(self, *names):
        return self.is_authenticated and self.role and self.role.name in names


class Genre(db.Model):
    __tablename__ = "genres"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False, unique=True)


class Book(db.Model):
    __tablename__ = "books"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(255), nullable=False)
    short_description = db.Column(db.Text, nullable=False)
    year = db.Column(db.Integer, nullable=False)
    publisher = db.Column(db.String(255), nullable=False)
    author = db.Column(db.String(255), nullable=False)
    page_count = db.Column(db.Integer, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    genres = db.relationship("Genre", secondary=book_genres, backref=db.backref("books", lazy="dynamic"))
    cover = db.relationship("Cover", back_populates="book", cascade="all, delete-orphan", uselist=False)
    reviews = db.relationship("Review", back_populates="book", cascade="all, delete-orphan")

    @property
    def approved_reviews(self):
        return [review for review in self.reviews if review.status and review.status.name == "одобрена"]

    @property
    def average_rating(self):
        reviews = self.approved_reviews
        if not reviews:
            return None
        return round(sum(review.rating for review in reviews) / len(reviews), 1)


class Cover(db.Model):
    __tablename__ = "covers"

    id = db.Column(db.Integer, primary_key=True)
    filename = db.Column(db.String(255), nullable=False)
    mime_type = db.Column(db.String(120), nullable=False)
    md5_hash = db.Column(db.String(32), nullable=False)
    book_id = db.Column(db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=False, unique=True)

    book = db.relationship("Book", back_populates="cover")


class ReviewStatus(db.Model):
    __tablename__ = "review_statuses"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False, unique=True)


class Review(db.Model):
    __tablename__ = "reviews"

    id = db.Column(db.Integer, primary_key=True)
    book_id = db.Column(db.Integer, db.ForeignKey("books.id", ondelete="CASCADE"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    rating = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    status_id = db.Column(db.Integer, db.ForeignKey("review_statuses.id"), nullable=False)

    book = db.relationship("Book", back_populates="reviews")
    user = db.relationship("User", back_populates="reviews")
    status = db.relationship("ReviewStatus")
    __table_args__ = (db.UniqueConstraint("book_id", "user_id", name="uq_review_book_user"),)


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY="dev-secret-key",
        SQLALCHEMY_DATABASE_URI=f"sqlite:///{BASE_DIR / 'library.db'}",
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        MAX_CONTENT_LENGTH=5 * 1024 * 1024,
    )
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    login_manager.init_app(app)
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    register_filters(app)
    register_routes(app)

    with app.app_context():
        db.create_all()
        seed_database()

    return app


def register_filters(app):
    @app.template_filter("markdown")
    def markdown_filter(text):
        html = markdown.markdown(text or "", extensions=["extra", "nl2br"])
        return bleach.clean(
            html,
            tags=bleach.sanitizer.ALLOWED_TAGS
            | {"p", "br", "pre", "code", "h1", "h2", "h3", "ul", "ol", "li"},
            attributes=bleach.sanitizer.ALLOWED_ATTRIBUTES,
        )


def register_routes(app):
    @app.route("/")
    def index():
        page = request.args.get("page", 1, type=int)
        pagination = (
            Book.query.outerjoin(Review)
            .group_by(Book.id)
            .order_by(Book.year.desc(), Book.title.asc())
            .paginate(page=page, per_page=10, error_out=False)
        )
        return render_template("index.html", pagination=pagination)

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if current_user.is_authenticated:
            return redirect(url_for("index"))
        if request.method == "POST":
            user = User.query.filter_by(login=request.form.get("login", "").strip()).first()
            if user and check_password_hash(user.password_hash, request.form.get("password", "")):
                login_user(user, remember=bool(request.form.get("remember")))
                return redirect(request.args.get("next") or url_for("index"))
            flash("Невозможно аутентифицироваться с указанными логином и паролем", "danger")
        return render_template("login.html")

    @app.route("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(request.referrer or url_for("index"))

    @app.route("/covers/<path:filename>")
    def cover_file(filename):
        return send_from_directory(UPLOAD_DIR, filename)

    @app.route("/books/<int:book_id>")
    def book_detail(book_id):
        book = db.get_or_404(Book, book_id)
        approved_reviews = Review.query.join(ReviewStatus).filter(
            Review.book_id == book.id,
            ReviewStatus.name == "одобрена",
        ).order_by(Review.created_at.desc()).all()
        own_review = None
        if current_user.is_authenticated:
            own_review = Review.query.filter_by(book_id=book.id, user_id=current_user.id).first()
        return render_template(
            "book_detail.html",
            book=book,
            approved_reviews=approved_reviews,
            own_review=own_review,
        )

    @app.route("/books/new", methods=["GET", "POST"])
    @login_required
    def book_create():
        if not current_user.has_role("администратор"):
            flash("У вас недостаточно прав для выполнения данного действия", "danger")
            return redirect(url_for("index"))
        return save_book()

    @app.route("/books/<int:book_id>/edit", methods=["GET", "POST"])
    @login_required
    def book_edit(book_id):
        if not current_user.has_role("администратор", "модератор"):
            flash("У вас недостаточно прав для выполнения данного действия", "danger")
            return redirect(url_for("index"))
        book = db.get_or_404(Book, book_id)
        return save_book(book)

    @app.route("/books/<int:book_id>/delete", methods=["POST"])
    @login_required
    def book_delete(book_id):
        if not current_user.has_role("администратор"):
            flash("У вас недостаточно прав для выполнения данного действия", "danger")
            return redirect(url_for("index"))
        book = db.get_or_404(Book, book_id)
        title = book.title
        cover_filename = book.cover.filename if book.cover else None
        db.session.delete(book)
        db.session.commit()
        remove_cover_if_unused(cover_filename)
        flash(f"Книга «{title}» успешно удалена", "success")
        return redirect(url_for("index"))

    @app.route("/books/<int:book_id>/reviews/new", methods=["GET", "POST"])
    @login_required
    def review_create(book_id):
        book = db.get_or_404(Book, book_id)
        if not current_user.has_role("администратор", "модератор", "пользователь"):
            flash("У вас недостаточно прав для выполнения данного действия", "danger")
            return redirect(url_for("index"))
        existing = Review.query.filter_by(book_id=book.id, user_id=current_user.id).first()
        if existing:
            flash("Вы уже оставили рецензию на эту книгу", "info")
            return redirect(url_for("book_detail", book_id=book.id))
        if request.method == "POST":
            try:
                review = Review(
                    book=book,
                    user=current_user,
                    rating=int(request.form["rating"]),
                    text=sanitize_markdown(request.form.get("text", "")),
                    status=get_status("на рассмотрении"),
                )
                validate_review(review)
                db.session.add(review)
                db.session.commit()
                flash("Рецензия отправлена на рассмотрение", "success")
                return redirect(url_for("book_detail", book_id=book.id))
            except Exception:
                db.session.rollback()
                flash("При сохранении рецензии возникла ошибка. Проверьте корректность введённых данных.", "danger")
        return render_template("review_form.html", book=book)

    @app.route("/my-reviews")
    @login_required
    def my_reviews():
        if not current_user.has_role("пользователь"):
            flash("У вас недостаточно прав для выполнения данного действия", "danger")
            return redirect(url_for("index"))
        reviews = Review.query.filter_by(user_id=current_user.id).order_by(Review.created_at.desc()).all()
        return render_template("my_reviews.html", reviews=reviews)

    @app.route("/moderation/reviews")
    @login_required
    def moderation_reviews():
        if not current_user.has_role("модератор"):
            flash("У вас недостаточно прав для выполнения данного действия", "danger")
            return redirect(url_for("index"))
        page = request.args.get("page", 1, type=int)
        pagination = (
            Review.query.join(ReviewStatus)
            .filter(ReviewStatus.name == "на рассмотрении")
            .order_by(Review.created_at.asc())
            .paginate(page=page, per_page=10, error_out=False)
        )
        return render_template("moderation_reviews.html", pagination=pagination)

    @app.route("/moderation/reviews/<int:review_id>", methods=["GET", "POST"])
    @login_required
    def moderation_review_detail(review_id):
        if not current_user.has_role("модератор"):
            flash("У вас недостаточно прав для выполнения данного действия", "danger")
            return redirect(url_for("index"))
        review = db.get_or_404(Review, review_id)
        if request.method == "POST":
            action = request.form.get("action")
            if action == "approve":
                review.status = get_status("одобрена")
                flash("Рецензия одобрена", "success")
            elif action == "reject":
                review.status = get_status("отклонена")
                flash("Рецензия отклонена", "success")
            else:
                abort(400)
            db.session.commit()
            return redirect(url_for("moderation_reviews"))
        return render_template("moderation_review_detail.html", review=review)


def save_book(book=None):
    genres = Genre.query.order_by(Genre.name).all()
    is_edit = book is not None
    if request.method == "POST":
        try:
            if not is_edit:
                book = Book()
                db.session.add(book)
            fill_book(book)
            selected_genres = Genre.query.filter(Genre.id.in_(request.form.getlist("genres"))).all()
            if not selected_genres:
                raise ValueError("genre is required")
            book.genres = selected_genres
            validate_book(book)
            db.session.flush()
            if not is_edit:
                uploaded_file = request.files.get("cover")
                if not uploaded_file or uploaded_file.filename == "":
                    raise ValueError("cover is required")
                save_cover(book, uploaded_file)
            db.session.commit()
            flash("Данные книги успешно сохранены", "success")
            return redirect(url_for("book_detail", book_id=book.id))
        except Exception:
            db.session.rollback()
            flash("При сохранении данных возникла ошибка. Проверьте корректность введённых данных.", "danger")
    return render_template("book_form.html", book=book, genres=genres, is_edit=is_edit)


def fill_book(book):
    book.title = request.form.get("title", "").strip()
    book.short_description = sanitize_markdown(request.form.get("short_description", ""))
    book.year = int(request.form.get("year", 0))
    book.publisher = request.form.get("publisher", "").strip()
    book.author = request.form.get("author", "").strip()
    book.page_count = int(request.form.get("page_count", 0))


def validate_book(book):
    if not all([book.title, book.short_description, book.publisher, book.author]):
        raise ValueError("required text field is empty")
    if book.year < 1 or book.year > datetime.now().year:
        raise ValueError("invalid year")
    if book.page_count < 1:
        raise ValueError("invalid page count")


def validate_review(review):
    if review.rating < 0 or review.rating > 5 or not review.text.strip():
        raise ValueError("invalid review")


def sanitize_markdown(text):
    return bleach.clean(text or "", tags=set(), attributes={}, strip=True)


def save_cover(book, uploaded_file):
    original_name = secure_filename(uploaded_file.filename)
    ext = original_name.rsplit(".", 1)[-1].lower() if "." in original_name else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise ValueError("unsupported image extension")
    data = uploaded_file.read()
    if not data:
        raise ValueError("empty image")
    import hashlib

    md5_hash = hashlib.md5(data).hexdigest()
    existing = Cover.query.filter_by(md5_hash=md5_hash).first()
    filename = existing.filename if existing else f"{book.id}.{ext}"
    cover = Cover(filename=filename, mime_type=uploaded_file.mimetype, md5_hash=md5_hash, book=book)
    db.session.add(cover)
    db.session.flush()
    if not existing:
        (UPLOAD_DIR / filename).write_bytes(data)


def remove_cover_if_unused(filename):
    if not filename:
        return
    if not Cover.query.filter_by(filename=filename).first():
        path = UPLOAD_DIR / filename
        if path.exists():
            path.unlink()


def get_status(name):
    return ReviewStatus.query.filter_by(name=name).one()


def seed_database():
    if not Role.query.first():
        roles = [
            Role(name="администратор", description="Суперпользователь, имеет полный доступ к системе."),
            Role(name="модератор", description="Редактирует книги и модерирует рецензии."),
            Role(name="пользователь", description="Оставляет рецензии."),
        ]
        db.session.add_all(roles)
    if not ReviewStatus.query.first():
        db.session.add_all(
            [
                ReviewStatus(name="на рассмотрении"),
                ReviewStatus(name="одобрена"),
                ReviewStatus(name="отклонена"),
            ]
        )
    if not Genre.query.first():
        db.session.add_all(
            [Genre(name=name) for name in ["Классика", "Фантастика", "Детектив", "Научпоп", "Роман"]]
        )
    db.session.commit()
    if not User.query.first():
        roles = {role.name: role for role in Role.query.all()}
        users = [
            User(
                login="admin",
                password_hash=make_password("admin"),
                last_name="Куриленко",
                first_name="Владислав",
                middle_name="Павлович",
                role=roles["администратор"],
            ),
            User(
                login="moderator",
                password_hash=make_password("moderator"),
                last_name="Иванова",
                first_name="Мария",
                middle_name="Сергеевна",
                role=roles["модератор"],
            ),
            User(
                login="user",
                password_hash=make_password("user"),
                last_name="Петров",
                first_name="Алексей",
                middle_name="Игоревич",
                role=roles["пользователь"],
            ),
        ]
        db.session.add_all(users)
        db.session.commit()
    if not Book.query.first():
        genres = Genre.query.all()
        book = Book(
            title="Пикник на обочине",
            short_description="Повесть о зоне, сталкерах и цене человеческих желаний.",
            year=1972,
            publisher="Молодая гвардия",
            author="Аркадий и Борис Стругацкие",
            page_count=192,
            genres=[genres[1], genres[0]],
        )
        db.session.add(book)
        db.session.flush()
        cover_path = UPLOAD_DIR / f"{book.id}.svg"
        cover_path.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="420" height="620">'
            '<rect width="420" height="620" fill="#243b53"/>'
            '<circle cx="300" cy="155" r="82" fill="#f6c453"/>'
            '<text x="36" y="420" font-size="42" fill="#ffffff" font-family="Arial">Пикник</text>'
            '<text x="36" y="474" font-size="42" fill="#ffffff" font-family="Arial">на обочине</text>'
            "</svg>",
            encoding="utf-8",
        )
        import hashlib

        md5_hash = hashlib.md5(cover_path.read_bytes()).hexdigest()
        db.session.add(Cover(filename=cover_path.name, mime_type="image/svg+xml", md5_hash=md5_hash, book=book))
        approved = get_status("одобрена")
        pending = get_status("на рассмотрении")
        user = User.query.filter_by(login="user").one()
        moderator = User.query.filter_by(login="moderator").one()
        db.session.add_all(
            [
                Review(book=book, user=user, rating=5, text="Сильная книга с тревожной атмосферой.", status=approved),
                Review(book=book, user=moderator, rating=4, text="Живая классика фантастики.", status=pending),
            ]
        )
        db.session.commit()


def make_password(password):
    return generate_password_hash(password, method="pbkdf2:sha256")


app = create_app()


if __name__ == "__main__":
    app.run(debug=True)
