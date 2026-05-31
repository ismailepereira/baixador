package com.baixador.data

enum class DownloadMode(val label: String, val emoji: String) {
    VIDEO("Vídeo", "🎬"),
    AUDIO("Áudio", "🎵"),
    PHOTO("Foto", "📷"),
}

enum class Quality(val label: String, val ytdlpFormat: String) {
    BEST("Melhor", "bestvideo*+bestaudio/best"),
    P1080("1080p", "bestvideo[height<=1080]+bestaudio/best[height<=1080]/best"),
    P720("720p", "bestvideo[height<=720]+bestaudio/best[height<=720]/best"),
    P480("480p", "bestvideo[height<=480]+bestaudio/best[height<=480]/best"),
    P360("360p", "bestvideo[height<=360]+bestaudio/best[height<=360]/best"),
}

enum class AudioQuality(val label: String, val ytdlpLevel: String) {
    BEST("Melhor (~245 kbps)", "0"),
    HIGH("Alta (~190 kbps)", "2"),
    MED("Média (~130 kbps)", "5"),
}
