package com.baixador.ui

import android.app.Application
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import com.baixador.BaixadorApp
import com.baixador.data.AudioQuality
import com.baixador.data.DownloadHub
import com.baixador.data.DownloadMode
import com.baixador.data.JobState
import com.baixador.data.JobStatus
import com.baixador.data.Quality
import com.baixador.service.DownloadService
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.map
import kotlinx.coroutines.flow.stateIn

class HomeViewModel(app: Application) : AndroidViewModel(app) {

    private val _url = MutableStateFlow("")
    val url: StateFlow<String> = _url.asStateFlow()

    private val _mode = MutableStateFlow(DownloadMode.VIDEO)
    val mode: StateFlow<DownloadMode> = _mode.asStateFlow()

    private val _quality = MutableStateFlow(Quality.P720)
    val quality: StateFlow<Quality> = _quality.asStateFlow()

    private val _audioQuality = MutableStateFlow(AudioQuality.BEST)
    val audioQuality: StateFlow<AudioQuality> = _audioQuality.asStateFlow()

    /** Lista ordenada por mais recente primeiro. */
    val jobs: StateFlow<List<JobStatus>> = DownloadHub.jobs
        .map { it.values.sortedByDescending { s -> s.job.createdAt } }
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5_000), emptyList())

    val ytdlpReady: Boolean
        get() = (getApplication<BaixadorApp>()).ytdlpReady

    val ytdlpError: String?
        get() = (getApplication<BaixadorApp>()).ytdlpInitError

    fun setUrl(value: String) { _url.value = value }
    fun setMode(value: DownloadMode) { _mode.value = value }
    fun setQuality(value: Quality) { _quality.value = value }
    fun setAudioQuality(value: AudioQuality) { _audioQuality.value = value }

    fun startDownload(): Boolean {
        val u = _url.value.trim()
        if (u.isBlank()) return false
        DownloadService.start(getApplication(), u, _mode.value, _quality.value, _audioQuality.value)
        return true
    }

    fun cancel(jobId: String) {
        DownloadService.cancel(getApplication(), jobId)
    }

    fun activeJob(): JobStatus? = jobs.value.firstOrNull {
        it.state is JobState.Running || it.state is JobState.Queued
    }
}
