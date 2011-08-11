# vim: tabstop=4 shiftwidth=4 softtabstop=4
import os
import string
import tempfile

from fabric.api import *
from pantheon import pantheon
from pantheon import logger
from pantheon import lygg

#TODO: Move logging into pantheon libraries for better coverage.
def configure_permissions(base_domain = "example.com",
                          require_group = None,
                          server_host = None):
    log = logger.logging.getLogger('pantheon.permissions.configure')
    log.info('Initialized permissions configuration.')
    try:
        server = pantheon.PantheonServer()

        if not server_host:
            server_host = "auth." + base_domain

        ldap_domain = _ldap_domain_to_ldap(base_domain)
        values = {'ldap_domain':ldap_domain,'server_host':server_host}

        template = pantheon.get_template('ldap-auth-config.preseed.cfg')
        ldap_auth_conf = pantheon.build_template(template, values)
        with tempfile.NamedTemporaryFile() as temp_file:
            temp_file.write(ldap_auth_conf)
            temp_file.seek(0)
            local("sudo debconf-set-selections " + temp_file.name)

        # /etc/ldap/ldap.conf
        template = pantheon.get_template('openldap.ldap.conf')
        openldap_conf = pantheon.build_template(template, values)
        with open('/etc/ldap/ldap.conf', 'w') as f:
            f.write(openldap_conf)

        # /etc/ldap.conf
        template = pantheon.get_template('pam.ldap.conf')
        ldap_conf = pantheon.build_template(template, values)
        with open('/etc/ldap.conf', 'w') as f:
            f.write(ldap_conf)

        # Restrict by group
        allow = ['root', 'sudo', 'hermes']
        if require_group:
            allow.append(require_group)

        with open('/etc/ssh/sshd_config', 'a') as f:
            f.write('\nAllowGroups %s\n' % (' '.join(allow)))
            f.write('UseLPK yes\n')
            f.write('LpkLdapConf /etc/ldap.conf\n')

        local("auth-client-config -t nss -p lac_ldap")

        with open('/etc/sudoers.d/002_pantheon_users', 'w') as f:
            f.write("# This file was generated by PANTHEON.\n")
            f.write("# PLEASE DO NOT EDIT THIS FILE DIRECTLY.\n#\n")
            f.write("# Additional sudoer directives can be added in: " + \
                    "/etc/sudoers.d/003_pantheon_extra\n")
            f.write("\n%" + '%s ALL=(ALL) ALL' % require_group)
        local('chmod 0440 /etc/sudoers.d/002_pantheon_users')

        # Add LDAP user to www-data, and ssl-cert groups.
        ssl_group = "ssl-cert"
        local('usermod -aG %s,%s %s' % (server.web_group, ssl_group, require_group))
        # Use sed because usermod may fail if the user does not already exist.
        #local('sudo sed -i "s/' + ssl_group + ':x:[0-9]*:/\\0' + require_group + ',/g" /etc/group')

        # Restart after ldap is configured so openssh-lpk doesn't choke.
        local("/etc/init.d/ssh restart")

        # Write the group to a file for later reference.
        server.set_ldap_group(require_group)

        # Make the git repo and www directories writable by the group
        local("chown -R %s:%s /var/git/projects" % (require_group, require_group))
        local("chmod -R g+w /var/git/projects")

        # Make the git repo and www directories writable by the group
        local("chown -R %s:%s /var/www" % (require_group, require_group))
        local("chmod -R g+w /var/www")

        # Set ACLs
        set_acl_groupwritability(require_group, '/var/www')
        set_acl_groupwritability(require_group, '/var/git/projects')
    except:
        log.exception('Permission configuration unsuccessful.')
        raise
    else:
        log.info('Permissions configuration successful.')
        ygg._api_request('POST', '/sites/self/legacy-phone-home', '"configure_permissions"')

def _ldap_domain_to_ldap(domain):
    return ','.join(['dc=%s' % part.lower() for part in domain.split('.')])

def set_acl_groupwritability(require_group, directory):
    """Set up ACLs for a directory."""
    local('setfacl --recursive --remove-all %s' % directory)
    local('setfacl --recursive --no-mask --modify mask:rwx %s' % directory)
    local('setfacl --recursive --no-mask --modify group:%s:rwx %s' % (require_group, directory))
    local('setfacl --recursive --modify default:mask:rwx %s' % directory)
    local('setfacl --recursive --modify default:group:%s:rwx %s' % (require_group, directory))

