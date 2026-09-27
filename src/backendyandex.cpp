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
    ++m_yandexGeneration; cancel("yandex-session"); cancel("yandex-library");
    stopYandexWave();
    m_settings.setValue("yandexDisconnected", false);
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
    ++m_yandexGeneration; cancel("yandex-session"); cancel("yandex-library"); cancel("catalog");
    for (int i = m_playlists.size() - 1; i >= 0; --i)
      if (m_playlists[i].toMap().value("remote").toBool()) m_playlists.removeAt(i);
    for (int i = m_favorites.size() - 1; i >= 0; --i)
      if (m_favorites[i].toMap().value("id").toString().startsWith("ym:")) m_favorites.removeAt(i);
    emit libraryChanged(); m_saveTimer.start();
    stopYandexWave(); cancelYandexDownloads();
    m_settings.setValue("yandexDisconnected", true);
    qunsetenv("YANDEX_MUSIC_TOKEN");
    qputenv("SUNG_YANDEX_LOGGED_OUT", "1");
    m_yandexUid.clear(); m_yandexAccount.clear();
    emit yandexChanged();
    home();
  });
}

void Backend::syncYandexLibrary() {
  if (m_yandexUid.isEmpty() || m_yandexBusy || m_processes.contains("yandex-library")) return;
  const auto generation = m_yandexGeneration;
  request("yandex-library", {{"op", "yandex-library"}}, [this, generation](const QVariantMap &data) {
    if (generation != m_yandexGeneration) return;
    if (!data.value("ok").toBool()) { notifyError(data.value("error").toString()); return; }
    if (data.value("uid").toString() != m_yandexUid) return;
    QVariantList favorites;
    for (const auto &v : m_favorites)
      if (!v.toMap().value("id").toString().startsWith("ym:")) favorites.append(v);
    favorites.append(data.value("favorites").toList());
    m_favorites = favorites;
    QVariantList playlists;
    for (const auto &v : m_playlists)
      if (!v.toMap().value("remote").toBool()) playlists.append(v);
    for (const auto &v : data.value("playlists").toList()) {
      auto p = v.toMap();
      for (const auto &old : m_playlists) {
        const auto previous = old.toMap();
        if (previous.value("id") == p.value("id") && previous.value("revision") == p.value("revision")) {
          p["tracks"] = previous.value("tracks");
          p["loaded"] = previous.value("loaded", false);
        }
      }
      playlists.append(p);
    }
    m_playlists = playlists;
    if (m_page == "library" && m_libraryId == "favorites") m_results.assign(m_favorites);
    emit libraryChanged(); m_saveTimer.start();
  });
}

void Backend::applyYandexPlaylist(const QVariantMap &playlist) {
  if (playlist.value("id").toString().isEmpty()) return;
  bool replaced = false;
  for (int i = 0; i < m_playlists.size(); ++i) {
    if (m_playlists[i].toMap().value("id") == playlist.value("id")) {
      m_playlists[i] = playlist; replaced = true; break;
    }
  }
  if (!replaced) m_playlists.append(playlist);
  if (m_page == "local" && m_libraryId == playlist.value("id").toString()) {
    m_title = playlist.value("title").toString();
    m_results.assign(playlist.value("tracks").toList());
    emit catalogChanged();
  }
  emit libraryChanged(); m_saveTimer.start();
}

void Backend::mutateYandex(QVariantMap args) {
  if (m_yandexBusy) { emit toast("Wait for the current Yandex change to finish"); return; }
  if (m_yandexUid.isEmpty()) { notifyError("Connect to Yandex Music first."); return; }
  m_yandexBusy = true; ++m_yandexGeneration;
  emit yandexChanged();
  const auto op = args.value("op").toString();
  const auto item = args.value("item").toMap();
  request("yandex-mutation", args, [this, op, item](const QVariantMap &data) {
    m_yandexBusy = false;
    emit yandexChanged();
    if (!data.value("ok").toBool()) { notifyError(data.value("error").toString()); return; }
    if (op == "yandex-like") {
      const auto id = data.value("id").toString();
      for (int i = m_favorites.size() - 1; i >= 0; --i)
        if (m_favorites[i].toMap().value("id").toString() == id) m_favorites.removeAt(i);
      if (data.value("liked").toBool()) m_favorites.prepend(item);
      if (m_page == "library" && m_libraryId == "favorites") m_results.assign(m_favorites);
      emit libraryChanged(); m_saveTimer.start();
    }
    if (data.contains("playlist")) applyYandexPlaylist(data.value("playlist").toMap());
    if (data.contains("deleted")) {
      const auto id = data.value("deleted").toString();
      for (int i = m_playlists.size() - 1; i >= 0; --i)
        if (m_playlists[i].toMap().value("id").toString() == id) m_playlists.removeAt(i);
      if (m_libraryId == id) library("playlists");
      emit libraryChanged(); m_saveTimer.start();
    }
    emit toast(data.value("warning", "Saved to Yandex Music").toString());
  });
}

void Backend::createYandexPlaylist(const QString &name, const QVariantList &items, bool fromQueue) {
  mutateYandex({{"op", "yandex-playlist-create"}, {"title", name}, {"items", fromQueue ? m_queue.rows : items}});
}

void Backend::openYandexPlaylist(const QString &id) {
  QString title = "Yandex Music";
  for (const auto &v : m_playlists)
    if (v.toMap().value("id").toString() == id) title = v.toMap().value("title").toString();
  navigate("local", title, m_page != "local" || m_libraryId != id, "local:" + id);
  m_libraryId = id; m_busy = true; emit catalogChanged();
  const auto generation = m_yandexGeneration;
  request("catalog", {{"op", "yandex-playlist-get"}, {"id", id}}, [this, id, generation](const QVariantMap &data) {
    if (m_libraryId != id || m_page != "local") return;
    m_busy = false;
    if (generation != m_yandexGeneration) { emit catalogChanged(); return; }
    if (!data.value("ok").toBool()) { notifyError(data.value("error").toString(), "catalog"); emit catalogChanged(); return; }
    applyYandexPlaylist(data.value("playlist").toMap());
    emit catalogChanged();
  });
}

void Backend::editYandexPlaylist(const QString &id, const QVariantList &rows) {
  for (const auto &v : m_playlists) {
    const auto p = v.toMap();
    if (p.value("id").toString() != id) continue;
    if (!p.value("loaded").toBool()) { notifyError("Open the playlist before editing its tracks."); return; }
    mutateYandex({{"op", "yandex-playlist-edit"}, {"id", id}, {"revision", p.value("revision")}, {"items", rows}});
    return;
  }
}

void Backend::setYandexCacheMode(const QString &mode) {
  if (!QStringList{"auto", "manual", "off"}.contains(mode)) return;
  m_settings.setValue("yandexCacheMode", mode);
  if (mode == "off") cancelYandexDownloads();
  emit yandexChanged();
}

void Backend::queueYandexDownload(const QString &id, bool assetsOnly) {
  if (!id.startsWith("ym:") || id == m_yandexDownloadingId) return;
  for (const auto &v : m_yandexDownloads) if (v.value("id").toString() == id) return;
  // Keep automatic playback jobs ahead of a long optional artwork backfill.
  const QVariantMap job{{"op", assetsOnly ? "yandex-cache-assets" : "yandex-cache"}, {"id", id}, {"limitBytes", qint64(yandexCacheLimitMb()) * 1024 * 1024}};
  if (assetsOnly) m_yandexDownloads.append(job); else m_yandexDownloads.prepend(job);
  nextYandexDownload();
}

void Backend::nextYandexDownload() {
  if (!m_yandexDownloadingId.isEmpty() || m_yandexDownloads.isEmpty()) return;
  const auto job = m_yandexDownloads.takeFirst();
  const auto id = job.value("id").toString();
  m_yandexDownloadingId = id;
  m_yandexDownloadStatus = QString("Downloading · %1 remaining").arg(m_yandexDownloads.size());
  emit yandexChanged();
  request("yandex-download", job, [this, id](const QVariantMap &data) {
    m_yandexDownloadingId.clear();
    m_yandexDownloadStatus = data.value("ok").toBool() ? (data.value("warnings").toList().isEmpty() ? "Downloads complete" : "Audio saved; some artwork or lyrics are unavailable") : data.value("error").toString();
    if (data.value("ok").toBool() && current().value("id").toString() == id && !data.value("art").toString().isEmpty()) {
      auto row = current(); row["art"] = data.value("art");
      auto rows = m_queue.rows; rows[m_index] = row; m_queue.reconcile(rows); emit trackChanged();
    }
    if (data.value("ok").toBool() && yandexCacheLimitMb() > 0) {
      request("yandex-auto-prune", {{"op", "yandex-cache-prune"}, {"limitBytes", qint64(yandexCacheLimitMb()) * 1024 * 1024},
                                   {"protected", QVariantList{current().value("id"), id}}}, [](const QVariantMap &) {});
    }
    emit yandexChanged();
    nextYandexDownload();
  });
}

void Backend::cacheYandexTrack(const QVariantMap &track) {
  if (yandexCacheMode() == "off") { emit toast("Enable manual or automatic downloads in Settings"); return; }
  queueYandexDownload(track.value("id").toString());
}

void Backend::cacheYandexCompanions() {
  request("yandex-cache-list", {{"op", "yandex-cache-list"}}, [this](const QVariantMap &data) {
    if (!data.value("ok").toBool()) { notifyError(data.value("error").toString()); return; }
    for (const auto &v : data.value("items").toList()) queueYandexDownload(v.toMap().value("id").toString(), true);
    if (data.value("items").toList().isEmpty()) { m_yandexDownloadStatus = "No downloaded tracks"; emit yandexChanged(); }
  });
}

void Backend::cancelYandexDownloads() {
  cancel("yandex-download"); cancel("yandex-cache-list");
  m_yandexDownloads.clear(); m_yandexDownloadingId.clear();
  m_yandexDownloadStatus = "Downloads cancelled";
  emit yandexChanged();
}

void Backend::initializeYandex() {
  const auto generation = m_yandexGeneration;
  request("yandex-session", {{"op", "account-status"}}, [this, generation](const QVariantMap &data) {
    if (generation != m_yandexGeneration) return;
    if (!data.value("ok").toBool()) return;
    if (!m_settings.contains("yandexCacheMode") && data.contains("cacheMode")) setYandexCacheMode(data.value("cacheMode").toString());
    if (!data.value("connected").toBool()) return;
    m_yandexUid = data.value("uid").toString();
    m_yandexAccount = data.value("accountName").toString();
    emit yandexChanged(); syncYandexLibrary();
  });
}

void Backend::waveEvent(const QString &type) {
  const auto song = current();
  if (m_waveSession.isEmpty() || song.value("_waveSession").toString() != m_waveSession) return;
  QVariantMap event{{"type", type}, {"timestamp", QDateTime::currentDateTimeUtc().toString(Qt::ISODateWithMs)},
                    {"trackId", song.value("id").toString().mid(3)},
                    {"totalPlayedSeconds", m_wavePlayedMs / 1000.0}, {"playedSeconds", duration() / 1000.0}};
  m_waveFeedbacks.append(QVariantMap{{"batch_id", song.value("_waveBatch")}, {"event", event}, {"from", song.value("_waveFrom")}});
}

void Backend::waveOutcome(bool finished) {
  if (m_waveFinishedToken == m_trackToken || m_waveStartedToken != m_trackToken) return;
  waveEvent(finished ? "trackFinished" : "skip");
  m_waveFinishedToken = m_trackToken;
}

void Backend::stopYandexWave() {
  waveOutcome(false);
  if (!m_waveSession.isEmpty() && !m_waveFeedbacks.isEmpty()) {
    request("wave-final", {{"op", "wave-next"}, {"session", m_waveSession}, {"seeds", m_waveSeeds},
                          {"feedbacks", m_waveFeedbacks}}, [](const QVariantMap &) {});
  }
  ++m_waveGeneration; cancel("yandex-wave");
  m_waveSession.clear(); m_waveFeedbacks.clear();
  m_waveBusy = false; m_waveAdvance = false; m_wavePlayedMs = 0;
  emit yandexChanged();
}

QStringList Backend::personalWaveSeeds() const {
  const auto settings = yandexWaveSettings();
  QStringList seeds{settings.value("context", "user:onyourwave").toString()};
  for (const auto key : {"diversity", "moodEnergy", "language"})
    if (settings.contains(key)) seeds.append(settings.value(key).toString());
  return seeds;
}

void Backend::applyYandexWaveSettings(const QVariantMap &settings) {
  m_settings.setValue("yandexWaveSettings", settings);
  if ((yandexWaveActive() || m_waveBusy) && yandexWavePersonal()) {
    stopYandexWave(); startYandexWave();
  } else emit yandexChanged();
}

void Backend::setYandexWaveSetting(const QString &key, const QString &seed) {
  if (!QStringList{"context", "diversity", "moodEnergy", "language"}.contains(key)) {
    qFatal("Unknown My Wave setting %s", qPrintable(key));
  }
  auto settings = yandexWaveSettings();
  if (settings.value(key).toString() == seed || (seed.isEmpty() && !settings.contains(key))) return;
  if (seed.isEmpty()) settings.remove(key); else settings.insert(key, seed);
  applyYandexWaveSettings(settings);
}

void Backend::resetYandexWaveSettings() {
  if (!yandexWaveSettings().isEmpty()) applyYandexWaveSettings({});
}

void Backend::loadYandexWaveOptions() {
  if (m_waveOptionsBusy || !m_waveOptions.isEmpty()) return;
  m_waveOptionsBusy = true;
  emit yandexChanged();
  request("yandex-wave-settings", {{"op", "wave-settings"}}, [this](const QVariantMap &data) {
    m_waveOptionsBusy = false;
    if (!data.value("ok").toBool()) { emit yandexChanged(); notifyError(data.value("error").toString()); return; }
    m_waveOptions = {{"contexts", data.value("contexts")}, {"groups", data.value("groups")}};
    emit yandexChanged();
  });
}

void Backend::startYandexWave(const QStringList &requested) {
  if (m_waveBusy) return;
  stopYandexWave();
  const auto seeds = requested.isEmpty() ? personalWaveSeeds() : requested;
  m_waveBusy = true; m_waveSeeds = seeds; m_waveTitle.clear();
  const auto generation = m_waveGeneration;
  emit yandexChanged();
  request("yandex-wave", {{"op", "wave-start"}, {"seeds", seeds}}, [this, generation](const QVariantMap &data) {
    if (generation != m_waveGeneration) return;
    m_waveBusy = false;
    if (!data.value("ok").toBool()) { emit yandexChanged(); notifyError(data.value("error").toString()); return; }
    const auto rows = playable(data.value("items").toList());
    if (rows.isEmpty()) { emit yandexChanged(); notifyError("My Wave returned no playable tracks. Try again."); return; }
    m_waveSession = data.value("session").toString();
    m_waveFrom = data.value("from").toString();
    m_waveTitle = data.value("title").toString();
    m_waveTerminated = data.value("terminated").toBool();
    m_queue.reconcile(rows); m_index = -1;
    setShuffle(false); setRepeat(0);
    emit yandexChanged(); playAt(0);
  });
}

void Backend::extendYandexWave(bool advance) {
  if (m_waveSession.isEmpty()) return;
  m_waveAdvance = m_waveAdvance || advance;
  if (m_waveBusy) return;
  if (m_waveTerminated) { m_waveAdvance = false; if (advance) { pause(); emit toast("My Wave session has ended"); } return; }
  m_waveBusy = true;
  const auto generation = m_waveGeneration;
  const auto feedbackCount = m_waveFeedbacks.size();
  QVariantList queue;
  for (int i = qMax(0, m_index); i < m_queue.count(); ++i) {
    const auto song = m_queue.get(i);
    if (song.value("id").toString().startsWith("ym:")) queue.append(song.value("id").toString().mid(3));
  }
  emit yandexChanged();
  request("yandex-wave", {{"op", "wave-next"}, {"seeds", m_waveSeeds}, {"session", m_waveSession},
                          {"from", m_waveFrom}, {"queue", queue}, {"feedbacks", m_waveFeedbacks}},
          [this, generation, feedbackCount](const QVariantMap &data) {
    if (generation != m_waveGeneration) return;
    m_waveBusy = false;
    if (!data.value("ok").toBool()) { m_waveAdvance = false; emit yandexChanged(); notifyError(data.value("error").toString()); return; }
    m_waveFeedbacks = m_waveFeedbacks.mid(feedbackCount);
    m_waveSession = data.value("session").toString(); m_waveFrom = data.value("from").toString();
    m_waveTerminated = data.value("terminated").toBool();
    auto rows = m_queue.rows;
    // Bound long wave sessions: retain 30 previous songs plus upcoming tracks.
    if (m_index > 30) { const int removed = m_index - 30; rows = rows.mid(removed); m_index -= removed; }
    QSet<QString> queued;
    for (int i = qMax(0, m_index); i < rows.size(); ++i) queued.insert(rows[i].toMap().value("id").toString());
    for (const auto &v : playable(data.value("items").toList())) {
      const auto id = v.toMap().value("id").toString();
      if (!queued.contains(id)) { rows.append(v); queued.insert(id); }
    }
    m_queue.reconcile(rows); m_saveTimer.start();
    const bool advance = m_waveAdvance; m_waveAdvance = false;
    emit yandexChanged(); emit libraryChanged();
    if (advance) {
      if (m_index + 1 < m_queue.count()) playAt(m_index + 1, 1);
      else { pause(); emit toast("No new wave tracks. Try My Wave again."); }
    }
  });
}

void Backend::pruneYandexCache() {
  request("yandex-cache-prune", {{"op", "yandex-cache-prune"}, {"limitBytes", qint64(yandexCacheLimitMb()) * 1024 * 1024},
                                {"protected", QVariantList{current().value("id")}}}, [this](const QVariantMap &data) {
    if (!data.value("ok").toBool()) { notifyError(data.value("error").toString()); return; }
    emit toast(QString("Removed %1 old downloads").arg(data.value("removed").toInt()));
    if (m_page == "home") home();
  });
}

void Backend::openMyWave() {
  if (m_page != "wave") navigate("wave", "Моя волна");
}
