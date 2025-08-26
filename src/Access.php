<?php

use Slim\Psr7\Request;
use Slim\Psr7\Response;
use League\OAuth2\Client\Provider\Google;
use Psr\Http\Message\ResponseInterface;
use Psr\Http\Message\ServerRequestInterface;
use Psr\Http\Server\MiddlewareInterface;
use Psr\Http\Server\RequestHandlerInterface;
use Slim\App;

session_cache_limiter('');
session_start();

class Access implements MiddlewareInterface
{
    private readonly Google $provider;
    private readonly array $users;
    private readonly string $basePath;
    private readonly string $verifyEndpoint;

    public function __construct(App $app)
    {
        $host = $_SERVER['HTTP_HOST'] ?? $_SERVER['SERVER_NAME'] ?? 'localhost';
        $scheme = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') ? 'https' : 'http';
        $this->basePath = $app->getBasePath();
        $this->verifyEndpoint = '/authorization-google';
        $this->provider = new Google([
            'clientId' => ConfigManager::get('GOOGLE_CLIENT_ID'),
            'clientSecret' => ConfigManager::get('GOOGLE_SECRET'),
            'redirectUri' => $scheme . '://' . $host . $this->basePath . $this->verifyEndpoint,
        ]);
        $this->users = explode(',', ConfigManager::get('USERS_ALLOWED'));
        // $this->verifyEndpoint = $config->googleVerificationUrl();
        $app->get($this->verifyEndpoint, function($request, $response) {
             $verified = $this->verifyGoogleCallback($request, $response);
            if ($verified) {
                return $response->withHeader('Location', "$this->basePath/")->withStatus(302);
            } else {
                $response->getBody()->write('Pendiente de verificar, ');
                return $response->withStatus(403);
            }
        });
        $app->addMiddleware($this);
    }

    #[Override]
    public function process(ServerRequestInterface $request, RequestHandlerInterface $handler): ResponseInterface
    {
        $route = $request->getUri()->getPath(); // Obtiene la ruta actual
        $rutasPermitidas = [$this->basePath . $this->verifyEndpoint, $this->basePath . '/ping'];
        // Si la ruta está permitida, se omite la autenticación
        if (in_array($route, $rutasPermitidas)) {
            return $handler->handle($request);
        }
        $user = $this->getUsername();
        if (!$user) {
            $response = new Response();
            return $response->withHeader('Location', $this->getLocationToLogin())->withStatus(302);
        } else if (!$this->isValidUser()) {
            $response = new Response();
            $response->getBody()->write("El usuario $user no tiene acceso permitido");
            return $response->withStatus(403);
        } else {
            return $handler->handle($request);
        }
    }

    public function getUsername(): mixed
    {
        return isset($_SESSION['user']['name']) ? $_SESSION['user']['name'] : null;
    }

    public function isValidUser(): bool
    {
        $email = isset($_SESSION['user']['email']) ? $_SESSION['user']['email'] : null;
        return $email && in_array($email, $this->users);
    }

    public function getLocationToLogin(): string
    {
        // No autenticado, redirigir a Google
        $authUrl = $this->provider->getAuthorizationUrl();
        $_SESSION['oauth2state'] = $this->provider->getState();
        return $authUrl;
    }

    public function verifyGoogleCallback(Request $request, Response $response): bool
    {
        $queryParams = $request->getQueryParams();

        if (!isset($queryParams['code']) || !isset($queryParams['state']) || $queryParams['state'] !== $_SESSION['oauth2state']) {
            unset($_SESSION['oauth2state']);
            $response->getBody()->write('Error de autenticación.');
            return false;
            // return $response->withStatus(400);
        }

        $token = $this->provider->getAccessToken('authorization_code', ['code' => $queryParams['code']]);
        $user = $this->provider->getResourceOwner($token);
        $email = $user->getEmail();

        if (!in_array($email, $this->users)) {
            return false;
            // return $response->withStatus(403)->write('Acceso denegado');
        } else {
            $_SESSION['user'] = ['name' => $user->getName(), 'email' => $email];
            return true;
            // return $response->withHeader('Location', '/dashboard')->withStatus(302);
        }
    }
}