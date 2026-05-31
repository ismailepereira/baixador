package com.baixador.data

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow

/**
 * Bridge entre o Service (que roda os downloads) e o ViewModel (que renderiza a UI).
 * Mantido como singleton de processo — sobrevive a rotações da Activity.
 */
object DownloadHub {

    private val _jobs = MutableStateFlow<Map<String, JobStatus>>(emptyMap())
    val jobs: StateFlow<Map<String, JobStatus>> = _jobs.asStateFlow()

    fun update(status: JobStatus) {
        _jobs.value = _jobs.value + (status.job.id to status)
    }

    fun get(id: String): JobStatus? = _jobs.value[id]

    fun remove(id: String) {
        _jobs.value = _jobs.value - id
    }

    fun activeCount(): Int =
        _jobs.value.values.count { it.state is JobState.Queued || it.state is JobState.Running }
}
