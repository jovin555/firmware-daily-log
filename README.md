# LFCS Daily Log

> Daily LFCS exam prep — file operations, systemd, networking, storage and service configuration from the Linux Foundation Certified System Administrator curriculum.

## Live Blog

**https://jovin555.github.io/lfcs-blog/**

A daily auto-generated study blog powered by [DeepSeek AI](https://deepseek.com) and built with [Quartz](https://quartz.jzhao.xyz).
A new post is published every day at 6:00 AM UTC via GitHub Actions.

## Repo

https://github.com/jovin555/lfcs-blog

## How It Works

1. GitHub Actions runs `.github/workflows/daily-post.yml` at 6:00 AM UTC
2. `generate_post.py` calls the DeepSeek API to generate the next day's post
3. The post is committed to `content/day-NN.md`
4. Quartz rebuilds and deploys to GitHub Pages

## Local Usage

```bash
# Generate the next day's post manually
python3 generate_post.py

# Generate a specific day
python3 generate_post.py --day 5

# Preview without writing
python3 generate_post.py --dry-run
```

## Related Blogs

| Blog | Topic | URL |
|------|-------|-----|
| LFCS | Linux Foundation Certified Sysadmin | https://jovin555.github.io/lfcs-blog/ |
| Zephyr RTOS | Threads, drivers, BLE, power management | https://jovin555.github.io/zephyr-blog/ |
| IEC 62304 | Medical device software compliance | https://jovin555.github.io/iec62304-blog/ |
| Embedded Linux | Kernel drivers, device tree, OTA | https://jovin555.github.io/embedded-linux-blog/ |
| Yocto Project | BitBake, recipes, BSP layers, images | https://jovin555.github.io/yocto-blog/ |

## Built With

- [Quartz v4](https://quartz.jzhao.xyz) — static site generator
- [DeepSeek API](https://platform.deepseek.com) — AI content generation
- GitHub Actions — daily cron automation
- GitHub Pages — free hosting
