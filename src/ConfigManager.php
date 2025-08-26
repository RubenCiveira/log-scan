<?php

namespace App;

class ConfigManager {
    private static $config = null;
    
    public static function load() {
        if (self::$config !== null) {
            return self::$config;
        }
        
        self::$config = [];
        $envFile = __DIR__ . '/../.env';
        
        if (file_exists($envFile)) {
            $lines = file($envFile, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
            foreach ($lines as $line) {
                $line = trim($line);
                
                // Ignorar comentarios y líneas vacías
                if (empty($line) || strpos($line, '#') === 0) {
                    continue;
                }
                
                // Separar clave y valor
                if (strpos($line, '=') !== false) {
                    list($key, $value) = explode('=', $line, 2);
                    self::$config[trim($key)] = trim($value, '"\'');
                }
            }
        }
        
        return self::$config;
    }
    
    public static function get($key, $default = null) {
        $config = self::load();
        return $config[$key] ?? $default;
    }
    
    public static function getPublicPath() {
        return self::get('PUBLIC_PATH', '/var/www/html');
    }
    
    public static function getDirectoryForHostname($hostname) {
        return self::getPublicPath() . '/' . $hostname;
    }

    public static function getPhpExecutable() {
        return self::get('PHP_EXECUTABLE', 'php');
    }
}
?>
