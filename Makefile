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

uninstall:
	@echo "Uninstalling $(APP_NAME)..."
	rm -rf $(INSTALL_DIR)
	rm -f $(BIN_DIR)/$(APP_NAME)
	rm -f $(ICON_DIR)/$(ICON_FILE)
	rm -f $(DESKTOP_DIR)/$(DESKTOP_FILE)

.PHONY: install uninstall
