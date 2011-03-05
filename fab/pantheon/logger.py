import logging
import logging.handlers
import logging.config
import ygg
import ConfigParser

class NullHandler(logging.Handler):
    def emit(self, record):
        pass

class DrushHandler(logging.Handler):
    def emit(self, record):
        send = {"drush": {"type": record.type,
                          "log_message": record.message,
                          "drush_message": record.drush_message,
                          "memory": record.memory,
                          "timestamp": record.timestamp,
                          "error": record.error},
                "source": 'drush',
                "command": record.command}
        ygg.send_event(record.name, send, ['source-drush', 'inbox', 'all'])

class ServiceHandler(logging.Handler):
    def emit(self, record):
        conf_file = '/etc/pantheon/monitoring.conf'
        try:
            cfg = ConfigParser.ConfigParser()
            cfg.readfp(open(conf_file))
        except IOError:
            log.exception('Configuration file could not be loaded.')
        except:
            log.exception('FATAL: Unhandled exception')
            raise

        service = record.name.split('.')[-1]
        saved_status = cfg.get(service, 'status')

        if record.levelname in ['ERROR']:
            status = 'ERR'
            cfg.set(service, 'status', status)
        if record.levelname in ['WARNING']:
            status = 'WARN'
            cfg.set(service, 'status', status)
        if record.levelname in ['INFO']:
            status = 'OK'
            cfg.set(service, 'status', status)

        # Writing our configuration file to 'monitoring.conf'
        with open(conf_file, 'wb') as cf:
            cfg.write(cf)

        if saved_status != status:
            send = {"status": status,
                    "message": record.message,
                    "type" : record.levelname}
            ygg.set_service(service, send)

class EventHandler(logging.Handler):
    def emit(self, record):
        source = record.name.split('.')[0]
        send = {source: {"message": record.message,
                         "type" : record.levelname,
                         "created": record.created,
                         "asctime": record.asctime},
                "source": source}
        labels = ['source-%s' % record.source, 'inbox', 'all']
        ygg.send_event(record.name, send, labels)

# register our custom handlers so they can be used by the config file
logging.handlers.DrushHandler = DrushHandler
logging.handlers.ServiceHandler = ServiceHandler
logging.handlers.EventHandler = EventHandler
logging.handlers.NullHandler = NullHandler

with open('/opt/pantheon/fab/pantheon/logging.conf', 'r') as f:
    logging.config.fileConfig(f)

