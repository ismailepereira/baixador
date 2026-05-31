package com.baixador.data

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Build
import android.os.Environment
import android.provider.MediaStore
import com.yausername.youtubedl_android.YoutubeDL
import com.yausername.youtubedl_android.YoutubeDLException
import com.yausername.youtubedl_android.YoutubeDLRequest
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.channelFlow
import kotlinx.coroutines.flow.flowOn
import java.io.File

class Downloader(private val context: Context) {

    private val workRoot: File by lazy {
        File(context.cacheDir, "downloads").apply { mkdirs() }
    }

    /**
     * Executa o download e emite [JobState] conforme progride.
     * Termina com Done (com a lista de arquivos salvos no Downloads público) ou Failed.
     */
    fun download(job: DownloadJob, resolvedUrl: String = job.url): Flow<JobState> = channelFlow {
        val jobDir = File(workRoot, job.id).apply { mkdirs() }
        try {
            val request = buildRequest(job, resolvedUrl, jobDir)
            send(JobState.Running(0f, -1, "Iniciando…"))

            val response = YoutubeDL.getInstance().execute(request, job.id) { progress, etaInSeconds, line ->
                trySend(JobState.Running(progress.coerceIn(0f, 100f), etaInSeconds, line))
            }

            if (response.exitCode != 0) {
                send(JobState.Failed("yt-dlp saiu com código ${response.exitCode}\n${response.err.take(500)}"))
                return@channelFlow
            }

            // Move arquivos baixados para Downloads/Baixador via MediaStore (público).
            val savedUris = mutableListOf<String>()
            jobDir.walkTopDown().filter { it.isFile }.forEach { file ->
                val uri = exportToDownloads(file, job.mode)
                if (uri != null) savedUris.add(uri.toString())
            }
            send(JobState.Done(savedUris))
        } catch (e: YoutubeDLException) {
            send(JobState.Failed(e.message ?: "Erro yt-dlp"))
        } catch (e: Exception) {
            send(JobState.Failed(e.message ?: "Erro inesperado"))
        } finally {
            runCatching { jobDir.deleteRecursively() }
        }
    }.flowOn(Dispatchers.IO)

    fun cancel(jobId: String) {
        runCatching { YoutubeDL.getInstance().destroyProcessById(jobId) }
    }

    private fun buildRequest(job: DownloadJob, url: String, outDir: File): YoutubeDLRequest {
        val request = YoutubeDLRequest(url)
        // Saída
        request.addOption("-o", File(outDir, "%(title).200B.%(ext)s").absolutePath)
        request.addOption("--no-mtime")
        request.addOption("--no-warnings")
        request.addOption("--newline")
        // Limites de sanidade
        request.addOption("--no-playlist")

        when (job.mode) {
            DownloadMode.VIDEO -> {
                request.addOption("-f", job.quality.ytdlpFormat)
                request.addOption("--merge-output-format", "mp4")
            }
            DownloadMode.AUDIO -> {
                request.addOption("-x")
                request.addOption("--audio-format", "mp3")
                request.addOption("--audio-quality", job.audioQuality.ytdlpLevel)
            }
            DownloadMode.PHOTO -> {
                // yt-dlp consegue puxar fotos/carrosséis do IG e Twitter
                request.addOption("--write-thumbnail")
                request.addOption("--no-write-info-json")
            }
        }
        return request
    }

    /**
     * Copia o arquivo para Downloads/Baixador via MediaStore (API 29+) ou
     * diretamente via filesystem (API <= 28). Retorna o Uri público resultante.
     */
    private fun exportToDownloads(source: File, mode: DownloadMode): Uri? {
        val mime = mimeFor(source, mode)
        val subfolder = "Download/Baixador"

        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val resolver = context.contentResolver
            val values = ContentValues().apply {
                put(MediaStore.Downloads.DISPLAY_NAME, source.name)
                put(MediaStore.Downloads.MIME_TYPE, mime)
                put(MediaStore.Downloads.RELATIVE_PATH, subfolder)
                put(MediaStore.Downloads.IS_PENDING, 1)
            }
            val uri = resolver.insert(MediaStore.Downloads.EXTERNAL_CONTENT_URI, values) ?: return null
            resolver.openOutputStream(uri)?.use { out -> source.inputStream().use { it.copyTo(out) } }
            values.clear()
            values.put(MediaStore.Downloads.IS_PENDING, 0)
            resolver.update(uri, values, null, null)
            uri
        } else {
            // API 26..28: precisa de WRITE_EXTERNAL_STORAGE (declarado no Manifest)
            @Suppress("DEPRECATION")
            val downloads = Environment.getExternalStoragePublicDirectory(Environment.DIRECTORY_DOWNLOADS)
            val dest = File(downloads, "Baixador").apply { mkdirs() }
            val target = File(dest, source.name)
            source.copyTo(target, overwrite = true)
            Uri.fromFile(target)
        }
    }

    private fun mimeFor(file: File, mode: DownloadMode): String {
        return when (file.extension.lowercase()) {
            "mp4", "m4v" -> "video/mp4"
            "webm" -> "video/webm"
            "mkv" -> "video/x-matroska"
            "mp3" -> "audio/mpeg"
            "m4a", "aac" -> "audio/mp4"
            "opus" -> "audio/ogg"
            "jpg", "jpeg" -> "image/jpeg"
            "png" -> "image/png"
            "webp" -> "image/webp"
            else -> if (mode == DownloadMode.AUDIO) "audio/*"
            else if (mode == DownloadMode.PHOTO) "image/*"
            else "video/*"
        }
    }
}
