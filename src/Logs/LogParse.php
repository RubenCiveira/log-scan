<?php
declare(strict_types=1);

namespace App\Logs;

/**
 * Parser de Apache access logs orientado a separar por host.
 *
 * Soporta:
 *  - combined:  %h %l %u %t "%r" %>s %b "%{Referer}i" "%{User-Agent}i"
 *  - combined+host: (combined) + " %{Host}i " al final
 *  - vcombined: %v %h %l %u %t "%r" %>s %b "%{Referer}i" "%{User-Agent}i"
 *
 * Estrategia de host:
 *  1) vhost si viene en vcombined
 *  2) host_header si está logueado con %{Host}i
 *  3) url_host si la request es absoluta (http[s]://...)
 */
final class LogParser
{
    public const FORMAT_COMBINED        = 'combined';
    public const FORMAT_COMBINED_HOST   = 'combined_host'; // combined + "%{Host}i"
    public const FORMAT_VCOMBINED       = 'vcombined';

    private string $format;
    private string $pattern;
    private bool   $emitParseErrors;

    public function __construct(string $format = self::FORMAT_COMBINED, bool $emitParseErrors = false)
    {
        $this->emitParseErrors = $emitParseErrors;
        $this->format = $format;

        switch ($format) {
            case self::FORMAT_VCOMBINED:
                // vhost host ident auth [date] "request" status bytes "referer" "ua"
                $this->pattern = '/^(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+"([^"]*)"\s+(\d{3})\s+(\S+)\s+"([^"]*)"\s+"([^"]*)"$/';
                break;

            case self::FORMAT_COMBINED_HOST:
                // host ident auth [date] "request" status bytes "referer" "ua" "Host"
                $this->pattern = '/^(\S+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+"([^"]*)"\s+(\d{3})\s+(\S+)\s+"([^"]*)"\s+"([^"]*)"\s+"([^"]*)"$/';
                break;

            case self::FORMAT_COMBINED:
            default:
                // host ident auth [date] "request" status bytes "referer" "ua"
                $this->pattern = '/^(\S+)\s+(\S+)\s+(\S+)\s+\[([^\]]+)\]\s+"([^"]*)"\s+(\d{3})\s+(\S+)\s+"([^"]*)"\s+"([^"]*)"$/';
                break;
        }
    }

    /** Itera un archivo (soporta .gz). Devuelve arrays con ['raw'=>string,'row'=>array|null] */
    public function iterate(string $path): \Generator
    {
        $gz = false;
        if (preg_match('/\.gz$/i', $path)) {
            $fh = @gzopen($path, 'rb');
            $gz = true;
        } else {
            $fh = @fopen($path, 'rb');
        }
        if (!$fh) {
            throw new \RuntimeException("Cannot open log file: {$path}");
        }

        while (($line = ($gz ? gzgets($fh) : fgets($fh))) !== false) {
            $line = rtrim($line, "\r\n");
            $row  = $this->parseLine($line);
            yield ['raw' => $line, 'row' => $row];
        }

        $gz ? gzclose($fh) : fclose($fh);
    }

    /** Parsea una línea; devuelve array de campos o null si no matchea (salvo emitParseErrors=true) */
    public function parseLine(string $line): ?array
    {
        if ($line === '') return null;

        if (!preg_match($this->pattern, $line, $m)) {
            return $this->emitParseErrors ? ['parse_error' => true, 'raw' => $line] : null;
        }

        // Map según formato
        if ($this->format === self::FORMAT_VCOMBINED) {
            // [1]=vhost [2]=ip [3]=ident [4]=auth [5]=date [6]=req [7]=status [8]=bytes [9]=ref [10]=ua
            $vhost      = $m[1];
            $remoteHost = $m[2];
            $identd     = $m[3] !== '-' ? $m[3] : null;
            $authUser   = $m[4] !== '-' ? $m[4] : null;
            $tsRaw      = $m[5];
            $request    = $m[6];
            $status     = (int)$m[7];
            $bytesRaw   = $m[8];
            $referer    = $m[9] !== '-' ? $m[9] : null;
            $userAgent  = $m[10] !== '-' ? $m[10] : null;
            $hostHeader = null;
        } elseif ($this->format === self::FORMAT_COMBINED_HOST) {
            // [1]=ip [2]=ident [3]=auth [4]=date [5]=req [6]=status [7]=bytes [8]=ref [9]=ua [10]=Host
            $vhost      = null;
            $remoteHost = $m[1];
            $identd     = $m[2] !== '-' ? $m[2] : null;
            $authUser   = $m[3] !== '-' ? $m[3] : null;
            $tsRaw      = $m[4];
            $request    = $m[5];
            $status     = (int)$m[6];
            $bytesRaw   = $m[7];
            $referer    = $m[8] !== '-' ? $m[8] : null;
            $userAgent  = $m[9] !== '-' ? $m[9] : null;
            $hostHeader = $m[10] !== '-' ? $m[10] : null;
        } else {
            // combined
            $vhost      = null;
            $remoteHost = $m[1];
            $identd     = $m[2] !== '-' ? $m[2] : null;
            $authUser   = $m[3] !== '-' ? $m[3] : null;
            $tsRaw      = $m[4];
            $request    = $m[5];
            $status     = (int)$m[6];
            $bytesRaw   = $m[7];
            $referer    = $m[8] !== '-' ? $m[8] : null;
            $userAgent  = $m[9] !== '-' ? $m[9] : null;
            $hostHeader = null; // no existe en combined puro
        }

        $timestamp = self::apacheTimeToIso8601($tsRaw);
        [$method, $url, $protocol, $urlPath, $urlQuery, $urlHost] = self::parseRequest($request);

        $bytes = null;
        if ($bytesRaw !== '-' && ctype_digit($bytesRaw)) {
            $bytes = (int)$bytesRaw;
        }

        return [
            '@timestamp'  => $timestamp,
            'vhost'       => $vhost,
            'host_header' => $hostHeader,
            'url_host'    => $urlHost,
            'remote_host' => $remoteHost,
            'identd_user' => $identd,
            'auth_user'   => $authUser,
            'request'     => $request ?: null,
            'method'      => $method,
            'url'         => $url,
            'protocol'    => $protocol,
            'url_path'    => $urlPath,
            'url_query'   => $urlQuery,
            'status'      => $status,
            'bytes'       => $bytes,
            'referer'     => $referer,
            'user_agent'  => $userAgent,
        ];
    }

    /** Resuelve el hostname “canónico” para agrupar (vhost > host_header > url_host) */
    public function resolveHost(array $row): ?string
    {
        foreach (['vhost', 'host_header', 'url_host'] as $k) {
            $val = $row[$k] ?? null;
            if (is_string($val) && $val !== '' && $val !== '-') {
                return strtolower($val);
            }
        }
        return null;
    }

    /** Cuenta ocurrencias por host (streaming-friendly) */
    public function countByHost(string $path): array
    {
        $counts = [];
        foreach ($this->iterate($path) as $item) {
            $row  = $item['row'];
            if (!$row || !empty($row['parse_error'])) continue;
            $host = $this->resolveHost($row) ?? 'unknown';
            $counts[$host] = ($counts[$host] ?? 0) + 1;
        }
        arsort($counts);
        return $counts;
    }

    /** Filtra y devuelve (yield) solo líneas de un host dado */
    public function filterByHost(string $path, string $wantedHost): \Generator
    {
        $wantedHost = strtolower($wantedHost);
        foreach ($this->iterate($path) as $item) {
            $row  = $item['row'];
            if (!$row || !empty($row['parse_error'])) continue;
            $host = $this->resolveHost($row);
            if ($host === $wantedHost) {
                yield $item; // ['raw'=>..., 'row'=>...]
            }
        }
    }

    /** Parte el log RAW en ficheros por host (cuidado con disco si hay muchos hosts) */
    public function splitRawByHost(string $path, string $outputDir): void
    {
        if (!is_dir($outputDir) && !mkdir($outputDir, 0775, true) && !is_dir($outputDir)) {
            throw new \RuntimeException("Cannot create output dir: {$outputDir}");
        }
        $handles = [];

        foreach ($this->iterate($path) as $item) {
            $raw = $item['raw'];
            $row = $item['row'];
            if ($row && empty($row['parse_error'])) {
                $host = $this->resolveHost($row) ?? 'unknown';
            } else {
                $host = 'unparsed';
            }
            $safe = preg_replace('/[^a-z0-9\.\-]+/i', '_', $host);
            $file = rtrim($outputDir, '/')."/access-{$safe}.log";
            if (!isset($handles[$file])) {
                $fh = fopen($file, 'ab');
                if (!$fh) continue;
                $handles[$file] = $fh;
            }
            fwrite($handles[$file], $raw . "\n");
        }

        foreach ($handles as $fh) {
            fclose($fh);
        }
    }

    /** Helpers */
    public static function apacheTimeToIso8601(string $t): ?string
    {
        $dt = \DateTime::createFromFormat('d/M/Y:H:i:s O', $t);
        return $dt ? $dt->format('c') : null;
    }

    /**
     * Devuelve [method, url, proto, path, query, urlHost]
     * - Si la URL del request es relativa, intenta extraer host cuando venga absoluta.
     */
    public static function parseRequest(string $req): array
    {
        $method = $url = $proto = null;
        if ($req !== '' && $req !== '-') {
            $parts = explode(' ', $req, 3);
            $method = $parts[0] ?? null;
            $url    = $parts[1] ?? null;
            $proto  = $parts[2] ?? null;
        }

        $path = $query = $urlHost = null;
        if ($url) {
            // Si es absoluta (http://host/...), parse_url nos da host.
            $pu = @parse_url($url);
            if (!is_array($pu) || !isset($pu['host'])) {
                // Si es relativa, prefija esquema ficticio para poder extraer path/query
                $pu = @parse_url('http://_/' . ltrim($url, '/'));
                if (is_array($pu)) {
                    $path  = $pu['path']  ?? null;
                    $query = $pu['query'] ?? null;
                }
            } else {
                $urlHost = $pu['host'] ?? null;
                $path    = $pu['path'] ?? null;
                $query   = $pu['query'] ?? null;
            }
        }

        return [$method, $url, $proto, $path, $query, $urlHost];
    }
}
