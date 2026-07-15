UUID := ai-token-bars@fen22.github.io
EXTENSION_DIR := $(HOME)/.local/share/gnome-shell/extensions/$(UUID)
CLAUDE_STATUSLINE := $(HOME)/.claude/ai-token-bars-statusline.py

.PHONY: check install configure-claude enable disable uninstall pack clean

check:
	node --check extension/extension.js
	python3 -m py_compile scripts/claude-statusline.py scripts/configure-claude-statusline.py
	python3 -m unittest discover -s tests
	python3 -m json.tool extension/metadata.json >/dev/null

install:
	mkdir -p "$(EXTENSION_DIR)"
	cp extension/extension.js extension/metadata.json extension/stylesheet.css "$(EXTENSION_DIR)/"
	install -m 700 scripts/claude-statusline.py "$(CLAUDE_STATUSLINE)"
	@echo "Installed $(UUID) to $(EXTENSION_DIR)"
	@echo "Run 'make configure-claude' to enable Claude Code statusLine support."

configure-claude:
	python3 scripts/configure-claude-statusline.py "$(CLAUDE_STATUSLINE)"

enable:
	gnome-extensions enable "$(UUID)"

disable:
	gnome-extensions disable "$(UUID)"

uninstall:
	gnome-extensions disable "$(UUID)" || true
	rm -rf "$(EXTENSION_DIR)"

pack: check
	mkdir -p dist
	gnome-extensions pack --force extension --out-dir dist

clean:
	rm -rf dist __pycache__ scripts/__pycache__
