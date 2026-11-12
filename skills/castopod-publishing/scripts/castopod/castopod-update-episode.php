#!/usr/bin/env php
<?php
// Update an existing episode: audio, show notes, title or native timed transcript.
// The audio keeps its stored file key, so the enclosure URL does not change and subscribers
// keep the episode they already have.
declare(strict_types=1);

require __DIR__ . '/castopod-bootstrap.php';

$o = getopt('', ['app:', 'podcast:', 'slug:', 'user:', 'audio:', 'description-file:', 'title:', 'transcript:', 'chapters:', 'expected-state:', 'number:']);
cp_boot(cp_opt($o, 'app', null, true));

use App\Entities\Episode;
use App\Models\EpisodeModel;
use App\Models\PodcastModel;
use CodeIgniter\Files\File;
use Modules\Auth\Models\UserModel;

$operationLock = cp_episode_lock(cp_opt($o, 'app', null, true), cp_opt($o, 'podcast', null, true), cp_opt($o, 'slug', null, true));

$episodeModel = new EpisodeModel();
$podcast = (new PodcastModel())->getPodcastByHandle(cp_opt($o, 'podcast', null, true));
if ($podcast === null) { fwrite(STDERR, "Podcast not found\n"); exit(1); }
$episode = $episodeModel->where(['podcast_id' => $podcast->id,
    'slug' => cp_opt($o, 'slug', null, true)])->first();
if (! $episode instanceof Episode) { fwrite(STDERR, "Episode not found\n"); exit(1); }

if (isset($o['expected-state'])) {
    $expected = json_decode(file_get_contents($o['expected-state']), true, 512, JSON_THROW_ON_ERROR);
    if ($expected != cp_episode_snapshot($episode)) {
        throw new RuntimeException('Episode changed since inspection; inspect before retrying');
    }
}
// Validate before setAudio/setTranscript/setChapters can write media.
if (isset($o['number'])) {
    if (!isset($o['expected-state']) || !preg_match('/^[0-9]+$/D', (string) $o['number']) || (int) $o['number'] < 1 ||
        array_intersect(['audio', 'description-file', 'title', 'transcript', 'chapters'], array_keys($o)) !== []) {
        throw new RuntimeException('Episode numbering requires a separate positive number-only conditional update');
    }
}
if (isset($o['chapters'])) {
    $file = $o['chapters'];
    if (!is_file($file) || strtolower(pathinfo($file, PATHINFO_EXTENSION)) !== 'json') {
        throw new RuntimeException('Chapters must be an existing JSON file');
    }
    $data = json_decode(file_get_contents($file), true, 512, JSON_THROW_ON_ERROR);
    if (($data['version'] ?? null) !== '1.2.0' || !is_array($data['chapters'] ?? null) || $data['chapters'] === []) {
        throw new RuntimeException('Invalid Podcasting 2.0 chapter file');
    }
    $last = -1;
    foreach ($data['chapters'] as $chapter) {
        $start = $chapter['startTime'] ?? null;
        if ((!is_int($start) && !is_float($start)) || !is_finite((float) $start) || $start <= $last ||
            $start < 0 || $start >= (float) $episode->getAudio()->duration ||
            !is_string($chapter['title'] ?? null) || trim($chapter['title']) === '') {
            throw new RuntimeException('Invalid chapter title or time');
        }
        $last = $start;
    }
    if ($data['chapters'][0]['startTime'] != 0) { throw new RuntimeException('Chapters must start at zero'); }
}

$user = (new UserModel())->where('username', cp_opt($o, 'user', null, true))->first();
if (! $user) { fwrite(STDERR, "User not found\n"); exit(1); }
$episode->updated_by = $user->id;

$changed = [];
if (isset($o['number'])) { $episode->number = (int) $o['number']; $changed[] = 'number'; }
if (isset($o['title'])) { $episode->title = (string) $o['title']; $changed[] = 'title'; }
if (isset($o['description-file'])) {
    $episode->description_markdown = file_get_contents($o['description-file']);
    $changed[] = 'description';
}
if (isset($o['audio'])) {
    $audio = $o['audio'];
    $ext = strtolower(pathinfo($audio, PATHINFO_EXTENSION));
    if (! is_file($audio) || ! in_array($ext, ['mp3', 'm4a'], true)) {
        fwrite(STDERR, "Audio must be an existing mp3 or m4a: {$audio}\n"); exit(1);
    }
    // the stored key keeps its old extension, so a replacement must be the same container
    $oldExt = strtolower(pathinfo($episode->getAudio()->file_key, PATHINFO_EXTENSION));
    if ($ext !== $oldExt) {
        fwrite(STDERR, "Episode audio is .{$oldExt}; replacing it with .{$ext} would break the enclosure URL\n"); exit(1);
    }
    $episode->setAudio(new File($audio));
    $changed[] = 'audio';
}
if (isset($o['transcript'])) {
    $file = $o['transcript'];
    $ext = strtolower(pathinfo($file, PATHINFO_EXTENSION));
    if (! is_file($file) || ! in_array($ext, ['srt', 'vtt'], true)) {
        fwrite(STDERR, "Transcript must be an existing srt or vtt\n"); exit(1);
    }
    $existing = $episode->getTranscript();
    if ($existing !== null && strtolower(pathinfo($existing->file_key, PATHINFO_EXTENSION)) !== $ext) {
        fwrite(STDERR, "Replacement transcript must retain its current format\n"); exit(1);
    }
    $episode->setTranscript(new File($file));
    $episode->transcript_remote_url = null;
    $episode->is_published_on_hubs = false;
    $changed[] = 'transcript';
}
if (isset($o['chapters'])) {
    $episode->setChapters(new File($o['chapters']));
    $episode->chapters_remote_url = null;
    $episode->is_published_on_hubs = false;
    $changed[] = 'chapters';
}
if ($changed === []) { fwrite(STDERR, "Nothing to change\n"); exit(1); }

if (! $episodeModel->update($episode->id, $episode)) {
    fwrite(STDERR, "Update failed: " . json_encode($episodeModel->errors()) . "\n"); exit(1);
}

$e = $episodeModel->getEpisodeById($episode->id);
echo json_encode([
    'id' => $e->id, 'slug' => $e->slug, 'changed' => $changed,
    'audio_file_size' => $e->getAudio()->file_size, 'duration' => (float) $e->audio->duration,
    'link' => $e->link, 'audio_url' => $e->audio_url,
], JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES), "\n";
