---
title: "Day 42: NFS Server, Samba & FTP"
date: 2026-07-24
tags: ["til", "lfcs", "nfs", "samba", "ftp"]
---

## What I Explored Today

Today I dove into three foundational network file-sharing protocols every Linux engineer must own: NFS (Network File System), Samba (SMB/CIFS), and FTP (File Transfer Protocol). These are not just exam topics—they are the backbone of file distribution in heterogeneous environments. I set up an NFSv4 server for Linux-to-Linux sharing, configured a Samba share for Windows clients, and locked down an FTP server with TLS. The goal was to understand not only the `systemctl` incantations but the security implications and performance trade-offs of each.

## The Core Concept

Why three protocols? Because no single protocol solves every problem.

- **NFS** is the native Unix way. It’s stateless in v3, stateful in v4, and integrates with Kerberos for auth. It’s fast over a trusted LAN but leaks metadata over WAN. Use it for internal cluster storage or home directories.
- **Samba** implements SMB/CIFS, the Windows-native protocol. It handles NTFS ACLs, printer sharing, and Active Directory integration. Use it when you must serve files to Windows clients or join a Windows domain.
- **FTP** (and its secure variants FTPS, SFTP) is the oldest. It’s simple, universally supported, but sends credentials in cleartext by default. Use it only for anonymous public downloads or legacy automation—never for sensitive data without TLS.

The engineer’s decision tree: *Is the client Linux? → NFS. Is the client Windows? → Samba. Is the client anything with a browser? → FTP (with TLS).*

## Key Commands / Configuration / Code

### 1. NFSv4 Server (Rocky Linux 9)

```bash
# Install packages
dnf install -y nfs-utils

# Create export directory
mkdir -p /srv/nfs/shared
chown nobody:nobody /srv/nfs/shared
chmod 755 /srv/nfs/shared

# Configure /etc/exports
# /srv/nfs/shared  client_ip(rw,sync,no_subtree_check,sec=sys)
echo "/srv/nfs/shared 192.168.1.0/24(rw,sync,no_subtree_check,sec=sys)" >> /etc/exports

# Export and verify
exportfs -rav
exportfs -v

# Enable and start services
systemctl enable --now nfs-server rpcbind nfs-mountd

# Firewall rules
firewall-cmd --permanent --add-service=nfs
firewall-cmd --reload
```

**Client mount:**
```bash
mount -t nfs4 -o rw,hard,intr 192.168.1.10:/srv/nfs/shared /mnt/nfs
```

### 2. Samba Share (Anonymous Guest Access)

```bash
# Install
dnf install -y samba samba-client

# Backup default config
cp /etc/samba/smb.conf /etc/samba/smb.conf.bak

# Write minimal config
cat > /etc/samba/smb.conf << 'EOF'
[global]
   workgroup = WORKGROUP
   server string = Samba Server
   security = user
   map to guest = Bad User
   log file = /var/log/samba/%m.log
   max log size = 50

[public]
   path = /srv/samba/public
   browseable = yes
   read only = no
   guest ok = yes
   create mask = 0755
EOF

# Create directory and set permissions
mkdir -p /srv/samba/public
chmod 777 /srv/samba/public

# Start services
systemctl enable --now smb nmb

# Firewall
firewall-cmd --permanent --add-service=samba
firewall-cmd --reload
```

**Test from Linux client:**
```bash
smbclient -L //192.168.1.10 -U guest
smbclient //192.168.1.10/public -U guest
```

### 3. FTP with TLS (vsftpd)

```bash
# Install
dnf install -y vsftpd openssl

# Generate self-signed cert (for testing only)
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/pki/tls/private/vsftpd.key \
  -out /etc/pki/tls/certs/vsftpd.crt \
  -subj "/C=US/ST=State/L=City/O=Org/CN=ftp.example.com"

# Configure vsftpd
cat > /etc/vsftpd/vsftpd.conf << 'EOF'
anonymous_enable=NO
local_enable=YES
write_enable=YES
local_umask=022
dirmessage_enable=YES
xferlog_enable=YES
connect_from_port_20=YES
xferlog_std_format=YES
chroot_local_user=YES
allow_writeable_chroot=YES
listen=YES
pam_service_name=vsftpd
userlist_enable=YES
userlist_deny=NO
userlist_file=/etc/vsftpd/user_list
tcp_wrappers=YES
ssl_enable=YES
allow_anon_ssl=NO
force_local_data_ssl=YES
force_local_logins_ssl=YES
rsa_cert_file=/etc/pki/tls/certs/vsftpd.crt
rsa_private_key_file=/etc/pki/tls/private/vsftpd.key
ssl_tlsv1=YES
ssl_sslv2=NO
ssl_sslv3=NO
EOF

# Add users allowed to FTP
echo "ftpuser" >> /etc/vsftpd/user_list

# Create user and start service
useradd -m ftpuser
passwd ftpuser
systemctl enable --now vsftpd

# Firewall
firewall-cmd --permanent --add-service=ftp
firewall-cmd --reload
```

**Test with explicit TLS:**
```bash
lftp -u ftpuser -e "set ftp:ssl-force true; ls; quit" 192.168.1.10
```

## Common Pitfalls & Gotchas

1. **NFS: `no_subtree_check` is your friend.** Without it, NFS performs extra directory traversal checks that break when clients mount subdirectories. Always add `no_subtree_check` unless you have a specific reason not to.

2. **Samba: SELinux blocks guest access by default.** If you see `NT_STATUS_ACCESS_DENIED` for guest shares, run `setsebool -P samba_export_all_rw on` or set the correct context on the share directory: `semanage fcontext -a -t samba_share_t '/srv/samba/public(/.*)?' && restorecon -Rv /srv/samba/public`.

3. **FTP: Passive mode and firewalls.** FTP uses two connections: control (port 21) and data (random high port). With `vsftpd`, set `pasv_min_port=30000` and `pasv_max_port=31000`, then open that range in the firewall. Without this, clients behind NAT will hang on directory listings.

## Try It Yourself

1. **NFS: Set up an NFSv4 export with Kerberos security (`sec=krb5p`).** You’ll need a KDC (Kerberos server) and keytab on both server and client. Verify with `mount -o sec=krb5p` and check `nfsstat -m`.

2. **Samba: Configure a domain-joined share with Active Directory.** Join the Linux server to a Windows AD domain using `realm join`, then set `security = ads` in smb.conf and map AD groups to share permissions.

3. **FTP: Harden vsftpd with chroot and passive port range.** Modify the config to restrict users to their home directories (`chroot_local_user=YES`), set a passive port range, and verify with `nmap -p 21,30000-31000 <server_ip>` that only those ports are open.

## Next Up

Tomorrow I’ll tackle three more essential services: **Postfix** for mail transport, **DHCP** for automatic IP assignment, and **BIND9** for DNS resolution. We’ll configure a minimal mail server, a DHCP pool with static reservations, and a caching-only DNS forwarder.
