# Электронная библиотека

АИС «Электронная библиотека», вариант 1: модерация рецензий.

Автор: Куриленко Владислав Павлович, группа 241-3211.

## Запуск

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python app.py
```

Приложение откроется на `http://127.0.0.1:5000`.

## Тестовые пользователи

| Роль | Логин | Пароль |
| --- | --- | --- |
| Администратор | `admin` | `admin` |
| Модератор | `moderator` | `moderator` |
| Пользователь | `user` | `user` |

## Проверка

```bash
.venv/bin/python -m pytest -q
```

## Деплой на Render

1. Загрузите проект в GitHub-репозиторий.
2. На Render создайте `New` -> `Web Service`.
3. Подключите GitHub-репозиторий с проектом.
4. Укажите настройки:
   - Build Command: `pip install -r requirements.txt`
   - Start Command: `gunicorn app:app`
5. После деплоя откройте выданную Render ссылку.
