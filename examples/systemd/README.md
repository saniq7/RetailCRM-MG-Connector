# Регулярная выгрузка через systemd

```bash
sudo useradd --system --home /var/lib/retailcrm-mg --create-home mg
sudo install -d -m 750 -o mg -g mg /etc/retailcrm-mg

sudo -u mg python3 -m venv /opt/retailcrm-mg/.venv
sudo -u mg /opt/retailcrm-mg/.venv/bin/pip install \
    git+https://github.com/saniq7/RetailCRM-MG-Connector.git

# токен выпускается один раз, от имени того же пользователя
sudo -u mg RETAILCRM_MG_ENV_FILE=/etc/retailcrm-mg/.env \
    /opt/retailcrm-mg/.venv/bin/retailcrm-mg bootstrap

sudo cp retailcrm-mg-export.* /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now retailcrm-mg-export.timer
```

Проверка:

```bash
systemctl list-timers retailcrm-mg-export.timer
journalctl -u retailcrm-mg-export.service -n 50
```

Файл `/etc/retailcrm-mg/.env` содержит токен — права `600`, владелец `mg`.
