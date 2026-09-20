import QtQuick
import QtQuick.Controls
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
}
