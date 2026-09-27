import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Sung.Native 1.0

Rectangle {
    id: root
    color: "#08090b"; radius: Theme.shapeExtraLarge; clip: true
    objectName: "myWavePage"
    property bool active: false
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
    RoundedArt {
        id: paletteSample; visible: false; pixels: 32; source: app.current.art || ""
        onReadyChanged: root.seed = ready ? seedColor() : "transparent"
    }
    property color seed: "transparent"
    property bool tuning: false
    onTuningChanged: if(tuning) app.loadYandexWaveOptions()
    onActiveChanged: if(!active) tuning = false
    // The server names a running personal wave; before it starts, the chosen
    // options preview that name.
    readonly property string waveTitle: {
        if(app.yandexWaveActive && app.yandexWavePersonal && app.yandexWaveTitle) return app.yandexWaveTitle
        const chosen = app.yandexWaveSettings, names = []
        for(const c of app.yandexWaveOptions.contexts || []) if(c.seed === chosen.context) names.push(c.name)
        for(const g of app.yandexWaveOptions.groups || [])
            for(const v of g.values) if(v.seed === chosen[g.key]) names.push(v.name)
        return names.length ? names.join(" · ") : "Моя волна"
    }
    function tint(offset, fallback) {
        if(seed.a === 0) return fallback
        return Qt.hsla(((seed.hslHue < 0 ? 0.78 : seed.hslHue) + offset + 1) % 1,
                       Math.max(0.6, seed.hslSaturation), 0.56, 1)
    }
    ShaderEffect {
        anchors.fill: parent
        visible: GraphicsInfo.api !== GraphicsInfo.Software
        property real phase: root.phase
        property real amplitude: root.level
        property real glow: root.glow
        property vector2d viewport: Qt.vector2d(width,height)
        property color tint1: root.tint(-0.12, "#7822ff")
        property color tint2: root.tint(0.07, "#ed2680")
        property color tint3: root.tint(0, "#edc400")
        fragmentShader: "qrc:/shaders/mywave.frag.qsb"
    }
    Item {
        anchors.centerIn: parent; width: Math.min(parent.width,parent.height)*0.9; height: width
        visible: GraphicsInfo.api === GraphicsInfo.Software
        Repeater {
            model: [root.tint(-0.12, "#7822ff"),root.tint(0.07, "#ed2680"),root.tint(0, "#edc400")]
            Rectangle {
                required property int index
                required property color modelData
                width: parent.width*(0.84-index*0.1); height: width
                x: (parent.width-width)/2+Math.sin(root.phase+index*2)*parent.width*0.1
                y: (parent.height-height)/2+Math.cos(root.phase*0.8+index)*parent.height*0.12
                radius: width*(0.36+0.1*Math.sin(root.phase+index)); rotation: root.phase*15+index*40
                color: modelData; opacity: 0.65
            }
        }
    }
    Artwork {
        anchors.centerIn: parent
        width: Math.min(parent.width,parent.height)*0.4; height: width
        visible: !!app.current.art
        url: app.current.art || ""; radius: 4; pixels: 640; crossfade: true
    }
    SungText {
        anchors.centerIn: parent; visible: !app.current.art
        text: "Моя волна"; color: "white"; font.weight: Font.Bold
        font.pixelSize: Math.max(28,Math.min(root.width,root.height)*0.1)
    }
    SungText {
        objectName: "myWaveTitle"
        anchors.horizontalCenter: parent.horizontalCenter; anchors.bottom: parent.bottom; anchors.bottomMargin: 24
        width: parent.width-48; horizontalAlignment: Text.AlignHCenter; elide: Text.ElideRight
        visible: root.waveTitle !== "Моя волна"
        text: root.waveTitle; color: "white"; font.pixelSize: Theme.titleMedium; font.weight: Font.DemiBold
    }
    MButton {
        objectName: "myWaveTune"
        anchors.top: parent.top; anchors.right: parent.right; anchors.margins: 16
        visible: app.yandexConnected
        text: "Настроить"; symbol: "filter"; tonal: true
        onClicked: root.tuning = !root.tuning
    }
    Rectangle {
        id: tunePanel
        objectName: "myWaveSettings"
        visible: root.tuning && app.yandexConnected
        anchors.top: parent.top; anchors.right: parent.right; anchors.topMargin: 72; anchors.rightMargin: 16
        width: Math.min(420, root.width-32)
        height: Math.min(tuneColumn.implicitHeight+32, root.height-88)
        radius: Theme.shapeLarge; color: Theme.container
        MElevation { anchors.fill: parent; radius: parent.radius; level: 2 }
        Flickable {
            anchors.fill: parent; anchors.margins: 16
            clip: true; contentHeight: tuneColumn.implicitHeight; boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            ColumnLayout {
                id: tuneColumn; width: parent.width; spacing: 8
                MLoadingIndicator {
                    Layout.alignment: Qt.AlignHCenter
                    visible: app.yandexWaveOptionsBusy; running: visible; label: "Загрузка настроек волны"
                }
                MButton {
                    Layout.alignment: Qt.AlignHCenter
                    visible: !app.yandexWaveOptionsBusy && !app.yandexWaveOptions.groups
                    text: "Повторить"; symbol: "refresh"; onClicked: app.loadYandexWaveOptions()
                }
                SungText {
                    visible: !!app.yandexWaveOptions.contexts
                    text: "Занятие"; color: Theme.muted; font.pixelSize: Theme.titleSmall; typeRole: "titleSmall"
                }
                Flow {
                    Layout.fillWidth: true; spacing: 8
                    visible: !!app.yandexWaveOptions.contexts
                    MChip {
                        text: "Любое"; selected: !app.yandexWaveSettings.context
                        onClicked: app.setYandexWaveSetting("context", "")
                    }
                    Repeater {
                        model: app.yandexWaveOptions.contexts || []
                        MChip {
                            required property var modelData
                            objectName: "waveContext_" + modelData.seed
                            text: modelData.name; selected: app.yandexWaveSettings.context === modelData.seed
                            onClicked: app.setYandexWaveSetting("context", modelData.seed)
                        }
                    }
                }
                Repeater {
                    model: app.yandexWaveOptions.groups || []
                    ColumnLayout {
                        id: group
                        required property var modelData
                        Layout.fillWidth: true; spacing: 8
                        SungText {
                            Layout.topMargin: 8
                            text: group.modelData.name; color: Theme.muted; font.pixelSize: Theme.titleSmall; typeRole: "titleSmall"
                        }
                        Flow {
                            Layout.fillWidth: true; spacing: 8
                            Repeater {
                                model: group.modelData.values
                                MChip {
                                    required property var modelData
                                    objectName: "waveSetting_" + modelData.seed
                                    text: modelData.name
                                    selected: modelData.unspecified ? !app.yandexWaveSettings[group.modelData.key]
                                                                    : app.yandexWaveSettings[group.modelData.key] === modelData.seed
                                    onClicked: app.setYandexWaveSetting(group.modelData.key, modelData.unspecified ? "" : modelData.seed)
                                }
                            }
                        }
                    }
                }
                MButton {
                    Layout.alignment: Qt.AlignRight; Layout.topMargin: 8
                    visible: !!app.yandexWaveOptions.groups
                    text: "Сбросить"; enabled: Object.keys(app.yandexWaveSettings).length > 0
                    onClicked: app.resetYandexWaveSettings()
                }
            }
        }
    }
}
