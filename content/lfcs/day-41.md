---
title: "Day 41: HTTP Servers: Apache & nginx"
date: 2026-07-23
tags: ["til", "lfcs", "apache", "nginx", "http"]
---

## What I Explored Today

Today I dove into the two dominant HTTP servers in the Linux ecosystem: Apache HTTPD and nginx. While both serve web content, their architectures, configuration philosophies, and performance characteristics differ significantly. I installed, configured, and tested both on a CentOS 9 VM, focusing on virtual hosting, TLS termination, and basic performance tuning. The goal wasn't just to get a "Hello World" page up, but to understand when to reach for each tool in production.

## The Core Concept

Apache and nginx represent two fundamentally different approaches to handling concurrent connections. Apache uses a process/thread-per-connection model (MPM prefork, worker, or event). Each client connection consumes a dedicated OS thread or process. This makes Apache predictable and stable under low-to-moderate load, but memory usage scales linearly with concurrent connections. Under 10,000 simultaneous connections, Apache's memory footprint becomes prohibitive.

Nginx uses an event-driven, asynchronous, non-blocking architecture. A single worker process handles thousands of connections using epoll (Linux) or kqueue (FreeBSD). This means nginx can serve static content with dramatically lower memory overhead. However, nginx cannot embed dynamic language interpreters (like mod_php in Apache). It relies on reverse-proxying to separate application servers (PHP-FPM, uWSGI, Gunicorn).

The practical takeaway: use Apache when you need `.htaccess` per-directory overrides, embedded interpreters, or compatibility with legacy applications. Use nginx when you need high concurrency, static file serving, or a reverse proxy/cache layer in front of application servers. Many production stacks use both: nginx as a reverse proxy terminating TLS and serving static assets, with Apache (or PHP-FPM) handling dynamic requests behind it.

## Key Commands / Configuration / Code

### Installing and Starting Both Servers

```bash
# Apache (httpd on RHEL/CentOS, apache2 on Debian)
sudo dnf install httpd -y
sudo systemctl enable --now httpd

# nginx
sudo dnf install nginx -y
sudo systemctl enable --now nginx

# Verify listening ports
ss -tlnp | grep -E ':(80|443) '
```

### Apache Virtual Host Configuration

```apache
# /etc/httpd/conf.d/example.com.conf
<VirtualHost *:80>
    ServerName example.com
    ServerAlias www.example.com
    DocumentRoot /var/www/example.com/public_html

    <Directory /var/www/example.com/public_html>
        Options -Indexes +FollowSymLinks
        AllowOverride All
        Require all granted
    </Directory>

    ErrorLog /var/log/httpd/example.com_error.log
    CustomLog /var/log/httpd/example.com_access.log combined
</VirtualHost>
```

Key points: `AllowOverride All` enables `.htaccess` files (performance cost). `Options -Indexes` disables directory listing. Always set `ServerName` to avoid the default catch-all behavior.

### nginx Server Block Configuration

```nginx
# /etc/nginx/conf.d/example.com.conf
server {
    listen 80;
    server_name example.com www.example.com;
    root /var/www/example.com/public_html;
    index index.html index.htm;

    location / {
        try_files $uri $uri/ =404;
    }

    # Deny access to hidden files
    location ~ /\. {
        deny all;
        access_log off;
        log_not_found off;
    }

    # Static asset caching
    location ~* \.(jpg|jpeg|png|gif|ico|css|js)$ {
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    access_log /var/log/nginx/example.com_access.log;
    error_log /var/log/nginx/example.com_error.log;
}
```

Note the `try_files` directive: nginx doesn't have a mod_dir equivalent. You must explicitly define how to handle directory requests. The `expires` directive sets cache headers for static assets—a simple performance win.

### Basic TLS Termination (nginx)

```nginx
server {
    listen 443 ssl http2;
    server_name example.com;

    ssl_certificate /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers on;

    # Rest of configuration...
}
```

## Common Pitfalls & Gotchas

1. **SELinux blocking file access**: On RHEL-based systems, SELinux enforces strict file context rules. If Apache or nginx returns 403 Forbidden but permissions look correct, check SELinux. Use `ls -Z` to view contexts and `restorecon -Rv /var/www/` to fix them. The httpd_sys_content_t context is required for web-accessible files.

2. **Port conflicts**: Both Apache and nginx default to port 80 and 443. If you install both for testing, only one can bind at a time. Either change the listening port in the config (e.g., `Listen 8080` for Apache) or stop one service before starting the other. Use `ss -tlnp` to verify which process owns the port.

3. **nginx try_files misconfiguration**: A common mistake is omitting the `try_files` directive or misordering the arguments. Without it, requests to `/some-directory/` will return 404 even if the directory exists. Always include `try_files $uri $uri/ =404;` in your location block.

## Try It Yourself

1. **Set up a name-based virtual host on Apache**: Create two separate DocumentRoot directories, configure two VirtualHost blocks with different ServerName values, and verify that `curl -H "Host: site1.local" http://localhost` returns different content than `site2.local`.

2. **Configure nginx as a reverse proxy**: Install a simple Python HTTP server on port 8000 (`python3 -m http.server 8000`), then configure an nginx location block to proxy_pass `http://127.0.0.1:8000`. Add caching headers and verify the X-Forwarded-For header is passed correctly.

3. **Benchmark static file serving**: Create 1000 small HTML files, then use `ab` (Apache Bench) or `wrk` to benchmark both servers serving these files. Compare requests per second and memory usage (`ps aux --sort=-%mem`). Document the difference.

## Next Up

Tomorrow, I'll cover network file sharing with NFS Server, Samba, and FTP. We'll compare kernel-level NFS exports against Samba's SMB/CIFS protocol for Windows interoperability, and discuss when FTP (vs SFTP/FTPS) still makes sense in 2026.
