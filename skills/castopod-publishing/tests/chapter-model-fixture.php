<?php
// Synthetic Castopod models for exercising the real CLI helpers without a database.
declare(strict_types=1);
namespace { define('CP_VERSION', 'synthetic-fixture'); }
namespace CodeIgniter { class Boot { public static function bootConsole($paths): void {} } }
namespace CodeIgniter\Files {
    class File {
        public function __construct(public string $path) {}
        public function __toString(): string { return $this->path; }
    }
}
namespace App\Entities {
    #[\AllowDynamicProperties]
    class Episode {
        public function __construct(array $values) {
            foreach ($values as $key => $value) { $this->$key = $value; }
            $this->publication_status = $values['status'];
            $this->season_number = $values['season'];
            $this->audio = (object) ['file_key' => $values['audio_file_key'],
                'file_size' => $values['audio_file_size'], 'duration' => $values['duration']];
            $this->transcript_remote_url = $values['transcript_url'];
            $this->chapters_remote_url = $values['chapters_url'];
        }
        public function getAudio(): object { return $this->audio; }
        public function getTranscript() { return null; }
        public function getChapters() {
            return $this->chapters_id === null ? null : (object) ['file_url' => 'https://example.org/chapters.json'];
        }
        public function setChapters($file): self {
            file_put_contents(getenv('CHAPTER_FIXTURE_MEDIA'), file_get_contents((string) $file));
            $this->chapters_id = 42;
            return $this;
        }
    }
}
namespace App\Models {
    class PodcastModel {
        public function getPodcastByHandle($handle): object {
            return (object) ['id' => 7, 'handle' => $handle, 'title' => 'Synthetic show', 'publication_status' => 'published'];
        }
    }
    class EpisodeModel {
        public function where($conditions): self { return $this; }
        public function first(): \App\Entities\Episode {
            return new \App\Entities\Episode(json_decode(file_get_contents(getenv('CHAPTER_FIXTURE_STATE')), true));
        }
        public function update($id, $episode): bool {
            file_put_contents(getenv('CHAPTER_FIXTURE_STATE'), json_encode(\cp_episode_snapshot($episode)));
            return true;
        }
        public function getEpisodeById($id): \App\Entities\Episode { return $this->first(); }
    }
}
namespace Modules\Auth\Models {
    class UserModel {
        public function where($key, $value): self { return $this; }
        public function first(): object { return (object) ['id' => 9]; }
    }
}
