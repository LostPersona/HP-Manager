from __future__ import annotations


DEFAULT_LOCALE = "en"
SUPPORTED_LOCALES = ("en", "ru")


TRANSLATIONS: dict[str, dict[str, str]] = {
    "en": {
        "app.title": "HP Manager",
        "app.header": "HealthPoints Manager",
        "app.subtitle": "Track party HP, detach player views for OBS, and sync values from a Google Doc.",
        "language.label": "Language",
        "language.en": "English",
        "language.ru": "Russian",
        "card.add_player": "Add Player",
        "card.players": "Players",
        "card.sync": "Document Sync Preview",
        "card.overlay_settings": "Fill Settings",
        "label.name": "Name",
        "label.current": "Current",
        "label.max": "Max",
        "label.temp": "Temp",
        "label.step": "Step",
        "label.source": "Google Doc link",
        "label.poll_seconds": "Poll seconds",
        "label.overlay_ratio": "Fill shape",
        "action.add_to_dashboard": "Add To Dashboard",
        "action.player_window": "Player Window",
        "action.hide_window": "Hide Window",
        "action.overlay": "Fill",
        "action.hide_overlay": "Hide Fill",
        "action.apply": "Apply",
        "action.remove": "Remove",
        "action.damage": "- HP",
        "action.heal": "+ HP",
        "action.fetch_doc": "Fetch Doc Now",
        "action.apply_parsed_lines": "Apply Parsed Lines",
        "action.load_example": "Load Example",
        "action.hide_sync": "Hide Sync",
        "action.show_sync": "Show Sync",
        "action.show_settings": "Show Settings",
        "action.hide_settings": "Hide Settings",
        "players.header": "Each player card keeps stats on top and actions below, so controls stay visible at smaller sizes.",
        "sync.enable": "Enable automatic Google Doc sync",
        "sync.help": "Supported lines look like `Artem: 32/45`, `Artem: 32/45 (10)`, or `Borin Spencer: 7/31 (5)`.\nUse a readable Google Doc link above to fetch text automatically, or paste fetched text into the box below.\nWhen sync mode is enabled, manual HP controls are hidden and the dashboard becomes display-focused.",
        "overlay.show_title": "Show character name above fill",
        "overlay.aspect.1:1": "Square (1:1)",
        "overlay.aspect.4:3": "Rectangle (4:3)",
        "overlay.window_title": "{name} Fill",
        "player.window_title": "{name} HP",
        "player.temp_hp": "Temp HP: {temp_hp}",
        "player.summary": "Visible HP: {current_hp}/{max_hp}    Temp: {temp_hp}",
        "player.default_name": "Unnamed",
        "status.ready": "Ready",
        "status.added": "Added {name}.",
        "status.removed": "Removed {name}.",
        "status.sync_applied": "Applied {applied} line(s) from sync preview.",
        "status.sync_applied_with_issues": "Applied {applied} line(s), with {issues} parse issue(s).",
        "status.example_loaded": "Loaded example sync lines.",
        "status.language_changed": "Language switched to {language}.",
        "status.fetching_doc": "Fetching Google Doc...",
        "status.doc_fetched": "Fetched Google Doc and applied {applied} line(s).",
        "status.fetch_failed": "Google Doc fetch failed: {message}",
        "status.sync_source_missing": "Add a Google Doc link first.",
        "status.sync_hidden": "Document sync preview hidden.",
        "status.sync_shown": "Document sync preview shown.",
        "status.settings_hidden": "Fill settings hidden.",
        "status.settings_shown": "Fill settings shown.",
        "dialog.parse_issues.title": "Parse issues",
        "dialog.parse_issues.message": "Line {line_number}: could not parse '{line}'",
        "dialog.fetch_failed.title": "Google Doc fetch failed",
        "error.sync.no_link": "No Google Doc link was provided.",
        "error.sync.bad_link": "Could not extract a Google Doc ID from the provided link.",
        "error.sync.access_denied": "Google denied access to the document export. Make sure the doc is shared so the app can read it.",
        "error.sync.not_found": "Google Doc not found. Check the link and document permissions.",
        "error.sync.http": "Google Doc export failed with HTTP {code}.",
        "error.sync.network": "Could not reach Google Docs: {reason}",
        "error.sync.html_response": "Received an HTML page instead of plain text. The document may require sign-in or block text export.",
        "error.sync.unknown": "Unexpected sync error: {message}",
    },
    "ru": {
        "app.title": "Менеджер HP",
        "app.header": "Менеджер очков здоровья",
        "app.subtitle": "Отслеживайте HP группы, выносите окна игроков для OBS и синхронизируйте значения из Google Doc.",
        "language.label": "Язык",
        "language.en": "Английский",
        "language.ru": "Русский",
        "card.add_player": "Добавить игрока",
        "card.players": "Игроки",
        "card.sync": "Предпросмотр синхронизации документа",
        "card.overlay_settings": "Настройки заливки",
        "label.name": "Имя",
        "label.current": "Текущее",
        "label.max": "Макс.",
        "label.temp": "Врем.",
        "label.step": "Шаг",
        "label.source": "Ссылка на Google Doc",
        "label.poll_seconds": "Интервал опроса",
        "label.overlay_ratio": "Форма заливки",
        "action.add_to_dashboard": "Добавить на панель",
        "action.player_window": "Окно игрока",
        "action.hide_window": "Скрыть окно",
        "action.overlay": "Заливка",
        "action.hide_overlay": "Скрыть заливку",
        "action.apply": "Применить",
        "action.remove": "Удалить",
        "action.damage": "- HP",
        "action.heal": "+ HP",
        "action.fetch_doc": "Загрузить документ",
        "action.apply_parsed_lines": "Применить строки",
        "action.load_example": "Загрузить пример",
        "action.hide_sync": "Скрыть синхронизацию",
        "action.show_sync": "Показать синхронизацию",
        "action.show_settings": "Показать настройки",
        "action.hide_settings": "Скрыть настройки",
        "players.header": "В карточке игрока характеристики находятся сверху, а действия снизу, чтобы кнопки не скрывались на маленьких окнах.",
        "sync.enable": "Включить автоматическую синхронизацию с Google Doc",
        "sync.help": "Поддерживаются строки вида `Artem: 32/45`, `Artem: 32/45 (10)` или `Borin Spencer: 7/31 (5)`.\nУкажите доступную ссылку на Google Doc выше для автозагрузки или вставьте полученный текст в поле ниже.\nКогда режим синхронизации включен, ручные HP-элементы скрываются, и панель работает как витрина значений.",
        "overlay.show_title": "Показывать имя персонажа над заливкой",
        "overlay.aspect.1:1": "Квадрат (1:1)",
        "overlay.aspect.4:3": "Прямоугольник (4:3)",
        "overlay.window_title": "Заливка: {name}",
        "player.window_title": "{name} HP",
        "player.temp_hp": "Временные HP: {temp_hp}",
        "player.summary": "Видимые HP: {current_hp}/{max_hp}    Врем.: {temp_hp}",
        "player.default_name": "Без имени",
        "status.ready": "Готово",
        "status.added": "Игрок {name} добавлен.",
        "status.removed": "Игрок {name} удален.",
        "status.sync_applied": "Применено строк из предпросмотра: {applied}.",
        "status.sync_applied_with_issues": "Применено строк: {applied}, проблем парсинга: {issues}.",
        "status.example_loaded": "Пример строк синхронизации загружен.",
        "status.language_changed": "Язык переключен: {language}.",
        "status.fetching_doc": "Загрузка Google Doc...",
        "status.doc_fetched": "Google Doc загружен, применено строк: {applied}.",
        "status.fetch_failed": "Не удалось загрузить Google Doc: {message}",
        "status.sync_source_missing": "Сначала добавьте ссылку на Google Doc.",
        "status.sync_hidden": "Предпросмотр синхронизации скрыт.",
        "status.sync_shown": "Предпросмотр синхронизации показан.",
        "status.settings_hidden": "Настройки заливки скрыты.",
        "status.settings_shown": "Настройки заливки показаны.",
        "dialog.parse_issues.title": "Проблемы парсинга",
        "dialog.parse_issues.message": "Строка {line_number}: не удалось разобрать '{line}'",
        "dialog.fetch_failed.title": "Не удалось загрузить Google Doc",
        "error.sync.no_link": "Ссылка на Google Doc не указана.",
        "error.sync.bad_link": "Не удалось извлечь идентификатор Google Doc из указанной ссылки.",
        "error.sync.access_denied": "Google не дал доступ к экспорту документа. Убедитесь, что документ открыт для чтения приложением.",
        "error.sync.not_found": "Google Doc не найден. Проверьте ссылку и права доступа к документу.",
        "error.sync.http": "Экспорт Google Doc завершился ошибкой HTTP {code}.",
        "error.sync.network": "Не удалось связаться с Google Docs: {reason}",
        "error.sync.html_response": "Вместо текста пришла HTML-страница. Возможно, документ требует входа или блокирует текстовый экспорт.",
        "error.sync.unknown": "Непредвиденная ошибка синхронизации: {message}",
    },
}


def normalize_locale(locale: str | None) -> str:
    if locale in SUPPORTED_LOCALES:
        return locale
    return DEFAULT_LOCALE


class Localizer:
    def __init__(self, locale: str | None = None) -> None:
        self.locale = normalize_locale(locale)

    def set_locale(self, locale: str) -> None:
        self.locale = normalize_locale(locale)

    def text(self, key: str, **kwargs: object) -> str:
        value = TRANSLATIONS.get(self.locale, {}).get(key)
        if value is None:
            value = TRANSLATIONS[DEFAULT_LOCALE].get(key, key)
        return value.format(**kwargs)

    def locale_name(self, locale: str) -> str:
        code = normalize_locale(locale)
        return self.text(f"language.{code}")
