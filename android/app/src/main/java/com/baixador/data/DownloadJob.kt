package com.baixador.data

import java.util.UUID

data class DownloadJob(
    val id: String = UUID.randomUUID().toString().take(12),
    val url: String,
    val mode: DownloadMode,
    val quality: Quality = Quality.P720,
    val audioQuality: AudioQuality = AudioQuality.BEST,
    val createdAt: Long = System.currentTimeMillis(),
)

sealed class JobState {
    data object Queued : JobState()
    data class Running(val percent: Float, val etaSeconds: Long, val line: String) : JobState()
    data class Done(val savedFiles: List<String>) : JobState()
    data class Failed(val message: String) : JobState()
    data object Cancelled : JobState()
}

data class JobStatus(
    val job: DownloadJob,
    val state: JobState,
)
