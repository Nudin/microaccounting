# Define variables
APP_NAME = microaccounting
INSTALL_DIR = /opt/$(APP_NAME)
BIN_DIR = /usr/local/bin
DESKTOP_DIR = /usr/share/applications
ICON_DIR = /usr/share/icons/hicolor/128x128/apps
ICON_FILE = $(APP_NAME).png
MAIN_SCRIPT = main.py
EXTRA_FILES = enhancedqtableview.py main_window.py
DESKTOP_FILE = $(APP_NAME).desktop
TRANSLATIONS_DIR = /usr/share/$(APP_NAME)/i18n

# Installation rules
install:
	@echo "Installing $(APP_NAME)..."
	install -d $(INSTALL_DIR)
	install -m 755 $(MAIN_SCRIPT) $(INSTALL_DIR)/
	install -m 644 $(EXTRA_FILES) $(INSTALL_DIR)/
	ln -sf $(INSTALL_DIR)/$(MAIN_SCRIPT) $(BIN_DIR)/$(APP_NAME)
	install -d $(ICON_DIR)
	install -m 644 $(ICON_FILE) $(ICON_DIR)/
	install -m 644 $(DESKTOP_FILE) $(DESKTOP_DIR)/
	mkdir -p $(TRANSLATIONS_DIR)
	install -m 644 i18n/microaccounting_de.qm $(TRANSLATIONS_DIR)/

uninstall:
	@echo "Uninstalling $(APP_NAME)..."
	rm -rf $(INSTALL_DIR)
	rm -f $(BIN_DIR)/$(APP_NAME)
	rm -f $(ICON_DIR)/$(ICON_FILE)
	rm -f $(DESKTOP_DIR)/$(DESKTOP_FILE)

main_window.py: main_window.ui
	pyuic6 -x main_window.ui -o main_window.py

ts:
	pyside6-lupdate main.py main_window.ui -ts i18n/microaccounting_de.ts

qm:
	lrelease i18n/microaccounting_de.ts -qm i18n/microaccounting_de.qm

translate: ts qm

build: main_window.py translate

.PHONY: install uninstall
