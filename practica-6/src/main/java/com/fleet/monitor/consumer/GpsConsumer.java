package com.fleet.monitor.consumer;

import com.fleet.monitor.config.RabbitMQConfig;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.stereotype.Component;

@Component
public class GpsConsumer {

    private static final Logger log = LoggerFactory.getLogger(GpsConsumer.class);

    @RabbitListener(queues = RabbitMQConfig.GPS_QUEUE)
    public void consumeGps(String message) {
        try {
            log.info("GPS recibido: {}", message);
            // TODO: persistir en base de datos
        } catch (Exception e) {
            log.error("Error procesando GPS: {}", e.getMessage());
        }
    }

}
