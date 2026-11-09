package com.fleet.monitor.config;

import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.DirectExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class RabbitMQConfig {

    public static final String GPS_QUEUE = "cola.gps.telemetria";
    public static final String TEMP_ALERT_QUEUE = "cola.alertas.temperatura";
    public static final String FUEL_QUEUE = "cola.combustible.nivel";
    public static final String NOTIFICATION_QUEUE = "cola.notificaciones";
    public static final String FLEET_EXCHANGE = "exchange.fleet";

    @Bean
    public DirectExchange fleetExchange() {
        return new DirectExchange(FLEET_EXCHANGE);
    }

    @Bean
    public Queue gpsQueue() {
        return new Queue(GPS_QUEUE, true);
    }

    @Bean
    public Queue tempAlertQueue() {
        return new Queue(TEMP_ALERT_QUEUE, true);
    }

    @Bean
    public Queue fuelQueue() {
        return new Queue(FUEL_QUEUE, true);
    }

    @Bean
    public Queue notificationQueue() {
        return new Queue(NOTIFICATION_QUEUE, true);
    }

    @Bean
    public Binding gpsBinding(Queue gpsQueue, DirectExchange fleetExchange) {
        return BindingBuilder.bind(gpsQueue).to(fleetExchange).with("gps.routing");
    }

    @Bean
    public Binding tempAlertBinding(Queue tempAlertQueue, DirectExchange fleetExchange) {
        return BindingBuilder.bind(tempAlertQueue).to(fleetExchange).with("temp.alert");
    }

    @Bean
    public Binding fuelBinding(Queue fuelQueue, DirectExchange fleetExchange) {
        return BindingBuilder.bind(fuelQueue).to(fleetExchange).with("fuel.routing");
    }

}
