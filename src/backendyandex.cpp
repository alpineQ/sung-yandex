#include "backend.h"
#include <QCoreApplication>
#include <QDateTime>
#include <QDir>
#include <QFileInfo>
#include <QStandardPaths>

void Backend::connectYandex(const QString &token, bool remember) {
  if (m_yandexBusy) return;
  const auto value = token.trimmed();
  if (value.isEmpty() || value.contains('\n') || value.contains('\r')) {
    notifyError("Enter a valid Yandex Music OAuth token.");
    return;
  }
  m_yandexBusy = true;
  emit yandexChanged();
  request("account", {{"op", "account-connect"}, {"token", value}, {"remember", remember}},
          [this, value](const QVariantMap &data) {
    m_yandexBusy = false;
    if (!data.value("ok").toBool()) {
      emit yandexChanged();
      notifyError(data.value("error").toString());
      return;
    }
    qputenv("YANDEX_MUSIC_TOKEN", value.toUtf8());
    qunsetenv("SUNG_YANDEX_LOGGED_OUT");
    m_yandexUid = data.value("uid").toString();
    m_yandexAccount = data.value("accountName").toString();
    emit yandexChanged();
    emit toast(data.value("remembered").toBool() ? "Connected · token saved in system keyring" : "Connected for this session");
    home();
  });
}

void Backend::disconnectYandex() {
  if (m_yandexBusy) return;
  m_yandexBusy = true;
  emit yandexChanged();
  request("account", {{"op", "account-forget"}}, [this](const QVariantMap &data) {
    m_yandexBusy = false;
    if (!data.value("ok").toBool()) {
      emit yandexChanged();
      notifyError(data.value("error").toString());
      return;
    }
    qunsetenv("YANDEX_MUSIC_TOKEN");
    qputenv("SUNG_YANDEX_LOGGED_OUT", "1");
    m_yandexUid.clear(); m_yandexAccount.clear();
    emit yandexChanged();
    home();
  });
}
