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
