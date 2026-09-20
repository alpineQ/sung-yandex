import QtQuick
import QtQuick.Controls
import QtQuick.Layouts

Item {
    id: root
    objectName: "myWavePage"
    property bool active: false
    readonly property bool compact: height < 430
    signal queueRequested()
    readonly property bool waveTrack: app.yandexWaveActive && !!app.current._waveSession
    readonly property bool animating: active && app.motion
    readonly property bool likedTrack: waveTrack && app.liked
    onLikedTrackChanged: if(active && likedTrack) likePulse.restart()
    property real phase: 3.0
    property real glow: 0
    property real level: waveTrack && app.playing ? Number(app.audioLevels[0] || 0) : 0
    Behavior on level { NumberAnimation { duration: 180 } }
    FrameAnimation {
        running: root.animating
        onTriggered: root.phase += Math.min(frameTime, 0.05) * (app.playing && root.waveTrack ? 0.65 : 0.22)
    }
    SequentialAnimation {
        id: likePulse
        NumberAnimation { target: root; property: "glow"; to: 0.8; duration: app.motion ? 160 : 0 }
        NumberAnimation { target: root; property: "glow"; to: 0; duration: app.motion ? 900 : 0 }
    }
    ColumnLayout {
        anchors.fill: parent
        spacing: root.compact ? 4 : 8
        SungText { text: "Моя волна"; heading: true; font.pixelSize: root.compact ? Theme.titleLarge : Theme.headlineMedium; Layout.alignment: Qt.AlignHCenter }
        SungText { visible: !root.compact; text: "Музыка, которая подстраивается под вас"; color: Theme.muted; horizontalAlignment: Text.AlignHCenter; wrapMode: Text.Wrap; Layout.fillWidth: true }
        Item {
            Layout.fillWidth: true; Layout.fillHeight: true; Layout.minimumHeight: root.compact ? 56 : 120
            ShaderEffect {
                anchors.centerIn: parent
                width: Math.min(parent.width, 720); height: parent.height
                visible: GraphicsInfo.api !== GraphicsInfo.Software
                property real phase: root.phase
                property real amplitude: root.level
                property real glow: root.glow
                property vector2d viewport: Qt.vector2d(width,height)
                fragmentShader: "qrc:/shaders/mywave.frag.qsb"
            }
            // Native scene-graph fallback when Qt has no shader-capable renderer.
            Item {
                anchors.centerIn: parent; width: Math.min(parent.width,parent.height)*0.8; height: width
                visible: GraphicsInfo.api === GraphicsInfo.Software
                Repeater {
                    model: ["#8655ff","#ec397d","#ffac40"]
                    Rectangle {
                        required property int index
                        required property string modelData
                        width: parent.width*(0.74-index*0.1); height: width
                        x: (parent.width-width)/2+Math.sin(root.phase+index*2)*parent.width*0.1
                        y: (parent.height-height)/2+Math.cos(root.phase*0.8+index)*parent.height*0.12
                        radius: width*(0.36+0.1*Math.sin(root.phase+index)); rotation: root.phase*15+index*40
                        color: modelData; opacity: 0.8
                        gradient: Gradient { GradientStop { position: 0; color: modelData } GradientStop { position: 1; color: Qt.lighter(modelData,1.4) } }
                    }
                }
            }
        }
        SungText {
            text: root.waveTrack ? app.current.title || "" : root.compact ? "Персональная музыка для вас" : "Каждый следующий трек — новое открытие"
            Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
            font.pixelSize: root.compact ? Theme.titleMedium : Theme.titleLarge; font.weight: Font.Medium
        }
        SungText {
            text: root.waveTrack ? app.current.artist || "" : "Нажмите «Слушать», чтобы начать"
            Layout.fillWidth: true; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight; color: Theme.muted
        }
        RowLayout {
            Layout.alignment: Qt.AlignHCenter; Layout.topMargin: root.compact ? 4 : 12; spacing: 12
            MButton { objectName: "waveLike"; symbol: app.liked ? "heart" : "heart_outline"; tip: "Мне нравится"; enabled: root.waveTrack && !app.yandexBusy; onClicked: app.toggleLike(app.current) }
            MButton {
                objectName: "wavePlay"; text: app.yandexWaveBusy && !root.waveTrack ? "Загружаем…" : root.waveTrack && app.playing ? "Пауза" : "Слушать"
                symbol: root.waveTrack && app.playing ? "pause" : "play"; filled: true; size: root.compact ? "small" : "medium"
                busy: app.yandexWaveBusy && !root.waveTrack; enabled: !busy
                onClicked: { if(root.waveTrack) { if(app.playing) app.pause(); else app.play(); } else app.startYandexWave(); }
            }
            MButton { objectName: "waveNext"; symbol: "next"; tip: "Следующий трек"; enabled: root.waveTrack; onClicked: app.next() }
        }
        RowLayout {
            Layout.alignment: Qt.AlignHCenter; Layout.bottomMargin: root.compact ? 0 : 8
            MButton { text: "Очередь"; symbol: "queue"; enabled: root.waveTrack; onClicked: root.queueRequested() }
            MButton { text: app.yandexWaveBusy && !root.waveTrack ? "Отменить" : "Новая волна"; enabled: !app.yandexWaveBusy || !root.waveTrack; onClicked: { if(app.yandexWaveBusy) app.stopYandexWave(); else app.startYandexWave(); } }
        }
    }
}
