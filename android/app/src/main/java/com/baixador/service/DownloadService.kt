package com.baixador.service

import android.app.Notification
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import com.baixador.MainActivity
import com.baixador.R
import com.baixador.data.AudioQuality
import com.baixador.data.DownloadHub
import com.baixador.data.DownloadJob
import com.baixador.data.DownloadMode
import com.baixador.data.Downloader
import com.baixador.data.JobState
import com.baixador.data.JobStatus
import com.baixador.data.Quality
import com.baixador.data.SpotifyResolver
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

class DownloadService : Service() {

    private val scope = CoroutineScope(Dispatchers.IO + SupervisorJob())
    private val running = mutableMapOf<String, Job>()
    private lateinit var downloader: Downloader
    private lateinit var spotifyResolver: SpotifyResolver

    override fun onCreate() {
        super.onCreate()
        downloader = Downloader(applicationContext)
        spotifyResolver = SpotifyResolver()
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> handleStart(intent)
            ACTION_CANCEL -> handleCancel(intent.getStringExtra(EXTRA_JOB_ID))
        }
        return START_NOT_STICKY
    }

    private fun handleStart(intent: Intent) {
        val url = intent.getStringExtra(EXTRA_URL).orEmpty()
        if (url.isBlank()) {
            stopIfIdle()
            return
        }
        val mode = DownloadMode.valueOf(intent.getStringExtra(EXTRA_MODE) ?: DownloadMode.VIDEO.name)
        val quality = Quality.valueOf(intent.getStringExtra(EXTRA_QUALITY) ?: Quality.P720.name)
        val audioQuality = AudioQuality.valueOf(intent.getStringExtra(EXTRA_AUDIO_QUALITY) ?: AudioQuality.BEST.name)

        val parent = DownloadJob(url = url, mode = mode, quality = quality, audioQuality = audioQuality)
        val notif = buildNotification("Preparando…", parent.id, indeterminate = true)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            startForeground(NOTIF_ID, notif, ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC)
        } else {
            startForeground(NOTIF_ID, notif)
        }

        val job = scope.launch {
            try {
                if (spotifyResolver.isSpotifyUrl(url)) {
                    DownloadHub.update(JobStatus(parent, JobState.Running(0f, -1, "Consultando Spotify…")))
                    val tracks = try {
                        spotifyResolver.resolve(url)
                    } catch (e: SpotifyResolver.NotConfiguredException) {
                        DownloadHub.update(JobStatus(parent, JobState.Failed(getString(R.string.spotify_not_configured))))
                        return@launch
                    }
                    if (tracks.isEmpty()) {
                        DownloadHub.update(JobStatus(parent, JobState.Failed("Spotify: nenhuma faixa encontrada")))
                        return@launch
                    }
                    tracks.forEachIndexed { idx, track ->
                        val sub = parent.copy(
                            id = "${parent.id}-${idx + 1}",
                            url = track.ytdlpQuery,
                            mode = DownloadMode.AUDIO,
                        )
                        runOneDownload(sub, track.ytdlpQuery, indexLabel = "${idx + 1}/${tracks.size}")
                    }
                    DownloadHub.update(JobStatus(parent, JobState.Done(emptyList())))
                } else {
                    runOneDownload(parent, url, indexLabel = null)
                }
            } finally {
                running.remove(parent.id)
                if (running.isEmpty()) stopIfIdle()
            }
        }
        running[parent.id] = job
    }

    private suspend fun runOneDownload(job: DownloadJob, url: String, indexLabel: String?) {
        downloader.download(job, url).collect { state ->
            DownloadHub.update(JobStatus(job, state))
            when (state) {
                is JobState.Running -> {
                    val pct = "%.0f".format(state.percent)
                    val prefix = indexLabel?.let { "[$it] " }.orEmpty()
                    updateNotification("${prefix}$pct% — ${state.line.take(60)}", job.id, state.percent.toInt())
                }
                is JobState.Done, is JobState.Failed, is JobState.Cancelled -> Unit
                else -> Unit
            }
        }
    }

    private fun handleCancel(jobId: String?) {
        if (jobId == null) return
        running[jobId]?.cancel()
        downloader.cancel(jobId)
        DownloadHub.get(jobId)?.let {
            DownloadHub.update(it.copy(state = JobState.Cancelled))
        }
        running.remove(jobId)
        stopIfIdle()
    }

    private fun stopIfIdle() {
        if (running.isEmpty()) {
            stopForeground(STOP_FOREGROUND_REMOVE)
            stopSelf()
        }
    }

    private fun buildNotification(text: String, jobId: String, progress: Int = 0, indeterminate: Boolean = false): Notification {
        val openApp = PendingIntent.getActivity(
            this, 0,
            Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        val cancelIntent = PendingIntent.getService(
            this, jobId.hashCode(),
            Intent(this, DownloadService::class.java).apply {
                action = ACTION_CANCEL
                putExtra(EXTRA_JOB_ID, jobId)
            },
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(this, getString(R.string.notification_channel_id))
            .setSmallIcon(R.drawable.ic_notification)
            .setContentTitle(getString(R.string.app_name))
            .setContentText(text)
            .setProgress(100, progress, indeterminate)
            .setOngoing(true)
            .setOnlyAlertOnce(true)
            .setContentIntent(openApp)
            .addAction(0, getString(R.string.cancel), cancelIntent)
            .build()
    }

    private fun updateNotification(text: String, jobId: String, progress: Int) {
        val nm = androidx.core.app.NotificationManagerCompat.from(this)
        if (nm.areNotificationsEnabled()) {
            nm.notify(NOTIF_ID, buildNotification(text, jobId, progress, indeterminate = progress <= 0))
        }
    }

    override fun onDestroy() {
        scope.coroutineContext[Job]?.cancel()
        super.onDestroy()
    }

    companion object {
        const val ACTION_START = "com.baixador.START"
        const val ACTION_CANCEL = "com.baixador.CANCEL"
        const val EXTRA_URL = "url"
        const val EXTRA_MODE = "mode"
        const val EXTRA_QUALITY = "quality"
        const val EXTRA_AUDIO_QUALITY = "audio_quality"
        const val EXTRA_JOB_ID = "job_id"
        private const val NOTIF_ID = 42

        fun start(
            context: Context,
            url: String,
            mode: DownloadMode,
            quality: Quality,
            audioQuality: AudioQuality,
        ) {
            val intent = Intent(context, DownloadService::class.java).apply {
                action = ACTION_START
                putExtra(EXTRA_URL, url)
                putExtra(EXTRA_MODE, mode.name)
                putExtra(EXTRA_QUALITY, quality.name)
                putExtra(EXTRA_AUDIO_QUALITY, audioQuality.name)
            }
            context.startForegroundService(intent)
        }

        fun cancel(context: Context, jobId: String) {
            val intent = Intent(context, DownloadService::class.java).apply {
                action = ACTION_CANCEL
                putExtra(EXTRA_JOB_ID, jobId)
            }
            context.startService(intent)
        }
    }
}
