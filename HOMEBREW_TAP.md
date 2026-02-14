# Создание Homebrew Tap для Clicker

## Шаг 1: Создать репозиторий homebrew-clicker

На GitHub создайте новый **публичный** репозиторий:
- Имя: `homebrew-clicker` (обязательно префикс `homebrew-`)
- Описание: "Homebrew tap for clicker"
- Public
- Без README, .gitignore, license (добавим вручную)

```bash
# Клонировать новый репозиторий
git clone https://github.com/spaceorc/homebrew-clicker.git
cd homebrew-clicker
```

## Шаг 2: Скопировать формулу

```bash
# Скопировать формулу из clicker/Formula/
cp /path/to/clicker/Formula/clicker.rb ./clicker.rb

# Создать README
cat > README.md <<'EOF'
# Homebrew Clicker

Homebrew tap for [clicker](https://github.com/spaceorc/clicker) - LLM-powered browser automation agent.

## Installation

```bash
brew tap spaceorc/clicker
brew install --HEAD clicker
```

## Usage

After installation, the `clicker` command will be available:

```bash
clicker --help
clicker "https://example.com" "Click the 'More' link"
```

## Uninstall

```bash
brew uninstall clicker
brew untap spaceorc/clicker
```
EOF

# Коммит
git add .
git commit -m "Add clicker formula"
git push origin main
```

## Шаг 3: Установить через Homebrew

После публикации репозитория пользователи смогут установить так:

```bash
# Добавить tap
brew tap spaceorc/clicker

# Установить clicker (из HEAD - последний коммит в master)
brew install --HEAD clicker

# Проверить установку
clicker --help
```

## Обновление формулы

Когда в clicker появятся изменения:

```bash
cd homebrew-clicker
# Скопировать обновленную формулу
cp /path/to/clicker/Formula/clicker.rb ./clicker.rb
git add clicker.rb
git commit -m "Update clicker formula"
git push

# Пользователи обновляются так:
brew update
brew upgrade --fetch-HEAD clicker
```

## Релизы (опционально, для будущего)

Когда создадите релиз v0.1.0 на GitHub:

1. Создайте релиз с тегом v0.1.0
2. Обновите формулу:

```ruby
class Clicker < Formula
  desc "LLM-powered browser automation agent"
  homepage "https://github.com/spaceorc/clicker"
  url "https://github.com/spaceorc/clicker/archive/refs/tags/v0.1.0.tar.gz"
  sha256 "..." # brew fetch --build-from-source spaceorc/clicker/clicker покажет SHA256
  license "MIT"

  # ... остальное как раньше
end
```

После этого пользователи смогут устанавливать стабильную версию:

```bash
brew install clicker  # без --HEAD
```

## Удаление tap

```bash
brew untap spaceorc/clicker
```

## Полезные команды

```bash
# Проверить формулу на ошибки
brew audit --strict clicker

# Тестировать установку локально
brew install --build-from-source --HEAD Formula/clicker.rb

# Переустановить с чистого листа
brew uninstall clicker
brew install --HEAD clicker
```
