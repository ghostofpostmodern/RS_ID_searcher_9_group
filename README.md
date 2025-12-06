# RS_ID_searcher_9_group
Репозиторий по проекту  создания телеграмм-бота, для поиска информации по RSID в NCBI

# 0. Как запустить:

После установки проекта 

docker compose build
docker compose up -d

# 1. Обзор системы

SNP-Frequency Bot — Telegram-бот, предназначенный для получения и визуализации популяционных частот
генетических вариантов по rsID через NCBI dbSNP API.

Основные функции:

- валидация пользовательского ввода rsID
- запрос к NCBI API
- извлечение частот аллелей
- расчёт генотипных частот по Харди–Вайнбергу
- построение графиков (PNG/JPEG/SVG/PDF)
- выдача текстового отчёта и структурированного JSON
- кэширование результатов (Redis, 24 ч)
- хранение истории запросов

Система построена как контейнеризованный сервис с одним приложением (ботом) и вспомогательными сервисами (Redis, Postgres).

---

# 2. Высокоуровневая архитектура

## 2.1. Client Layer

- Telegram Messenger
- Telegram Bot API

## 2.2. Application Layer (Python)

Компоненты:

- `bot.py` — Telegram-интерфейс
- `ncbi_client.py` — клиент NCBI API
- `snp_analyzer.py` — логика анализа
- `plot_generator.py` — визуализация
- `cache_manager.py` — кэш
- `storage.py` — история запросов
- `config.py` — конфигурация
- `logging_config.py` — настройка логов

## 2.3. Infrastructure Layer

- Docker + Docker Compose
- Redis — кэш
- ENV-переменные для токена, таймаутов и лимитов.

---

# 3. Поток данных (упрощённо)

1. Пользователь отправляет `/get rs12345` в Telegram.
2. `bot.py` валидирует rsID, показывает прогресс.
3. `cache_manager` проверяет наличие закэшированного результата.
4. При промахе кэша вызывается `ncbi_client.fetch_snp(rsid)`.
5. `snp_analyzer` преобразует ответ API в частоты аллелей и генотипов.
6. `plot_generator` строит графики и сохраняет их в файлы.
7. `bot.py` отправляет пользователю текстовый отчёт и изображения.
8. Результат сохраняется в кэш и историю запросов.

---

# 4. Компоненты

- Bot Layer (`bot.py`): команды `/start`, `/help`, `/get`, `/about`, `/history`.
- NCBI Client (`ncbi_client.py`): HTTP-запросы, таймауты, обработка ошибок.
- Business Logic (`snp_analyzer.py`): расчёты, агрегация, Hardy–Weinberg.
- Visualization (`plot_generator.py`): построение графиков.
- Caching (`cache_manager.py`): работа с Redis.
- History (`storage.py`): история запросов пользователя.
- Config (`config.py`): чтение переменных окружения.
- Logging (`logging_config.py`): базовая настройка логирования.

---

# 5. Контейнеризация

- `Dockerfile`: образ приложения с Python, зависимостями и кодом.
- `docker-compose.yml`: сервис `bot` + сервис `redis` (и, при необходимости, `postgres`).

---
