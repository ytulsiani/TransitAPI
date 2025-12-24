package com.mbta;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.mbta.mbtaapi.DirectionService;
import com.mbta.mbtaapi.LineService;
import com.mbta.mbtaapi.MbtaClient;
import com.mbta.mbtaapi.PredictionRequest;
import com.mbta.mbtaapi.PredictionService;
import com.mbta.mbtaapi.StopService;
import io.javalin.Javalin;
import java.io.IOException;
import java.util.Map;
import java.util.concurrent.ExecutionException;

public class App {
    public static void main(String[] args) {
        ObjectMapper objectMapper = new ObjectMapper();
        MbtaClient mbtaClient = new MbtaClient(objectMapper);
        LineService lineService = new LineService(mbtaClient);
        StopService stopService = new StopService(mbtaClient);
        DirectionService directionService = new DirectionService(mbtaClient);
        PredictionService predictionService = new PredictionService(mbtaClient);
        Javalin app = Javalin.create(config -> config.plugins.enableDevLogging());

        app.get("/health", ctx -> ctx.json(Map.of("status", "ok")));


        app.get(
                "/lines",
                ctx -> {
                    try {
                        ctx.json(Map.of("lines", lineService.getLines()));
                    } catch (ExecutionException e) {
                        ctx.status(502)
                                .json(
                                        Map.of(
                                                "error",
                                                "Failed to fetch lines",
                                                "details",
                                                e.getCause() != null
                                                        ? e.getCause().getMessage()
                                                        : e.getMessage()));
                    } catch (IOException e) {
                        ctx.status(502)
                                .json(
                                        Map.of(
                                                "error",
                                                "Failed to fetch lines",
                                                "details",
                                                e.getMessage()));
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        ctx.status(502)
                                .json(
                                        Map.of(
                                                "error",
                                                "Request interrupted",
                                                "details",
                                                "MBTA request was interrupted"));
                    }
                });

        app.get(
                "/directions",
                ctx -> {
                    String routeId = ctx.queryParam("route");
                    if (routeId == null || routeId.isBlank()) {
                        ctx.status(400)
                                .json(
                                        Map.of(
                                                "error",
                                                "Missing required query parameter 'route'"));
                        return;
                    }

                    try {
                        ctx.json(Map.of("directions", directionService.getDirections(routeId)));
                    } catch (IllegalArgumentException e) {
                        ctx.status(400)
                                .json(
                                        Map.of(
                                                "error",
                                                "Invalid route",
                                                "details",
                                                e.getMessage()));
                    } catch (ExecutionException e) {
                        ctx.status(502)
                                .json(
                                        Map.of(
                                                "error",
                                                "Failed to fetch directions",
                                                "details",
                                                e.getCause() != null
                                                        ? e.getCause().getMessage()
                                                        : e.getMessage()));
                    } catch (IOException e) {
                        ctx.status(502)
                                .json(
                                        Map.of(
                                                "error",
                                                "Failed to fetch directions",
                                                "details",
                                                e.getMessage()));
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        ctx.status(502)
                                .json(
                                        Map.of(
                                                "error",
                                                "Request interrupted",
                                                "details",
                                                "MBTA request was interrupted"));
                    }
                });

        app.get(
                "/stops",
                ctx -> {
                    String routeId = ctx.queryParam("route");
                    if (routeId == null || routeId.isBlank()) {
                        ctx.status(400)
                                .json(
                                        Map.of(
                                                "error",
                                                "Missing required query parameter 'route'"));
                        return;
                    }

                    try {
                        ctx.json(Map.of("stops", stopService.getStops(routeId)));
                    } catch (IllegalArgumentException e) {
                        ctx.status(400)
                                .json(
                                        Map.of(
                                                "error",
                                                "Invalid route",
                                                "details",
                                                e.getMessage()));
                    } catch (ExecutionException e) {
                        ctx.status(502)
                                .json(
                                        Map.of(
                                                "error",
                                                "Failed to fetch stops",
                                                "details",
                                                e.getCause() != null
                                                        ? e.getCause().getMessage()
                                                        : e.getMessage()));
                    } catch (IOException e) {
                        ctx.status(502)
                                .json(
                                        Map.of(
                                                "error",
                                                "Failed to fetch stops",
                                                "details",
                                                e.getMessage()));
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        ctx.status(502)
                                .json(
                                        Map.of(
                                                "error",
                                                "Request interrupted",
                                                "details",
                                                "MBTA request was interrupted"));
                    }
                });

        app.post(
                "/predictions",
                ctx -> {
                    try {
                        PredictionRequest predictionRequest = ctx.bodyAsClass(PredictionRequest.class);

                        if (predictionRequest == null || predictionRequest.stopId == null
                                || predictionRequest.stopId.isBlank()) {
                            ctx.status(400)
                                    .json(
                                            Map.of(
                                                    "error",
                                                    "Missing required field 'stopId'"));
                            return;
                        }

                        ctx.json(
                                Map.of(
                                        "predictions",
                                        predictionService.getPredictions(predictionRequest)));
                    } catch (IllegalArgumentException e) {
                        ctx.status(400)
                                .json(
                                        Map.of(
                                                "error",
                                                "Invalid request",
                                                "details",
                                                e.getMessage()));
                    } catch (IOException e) {
                        ctx.status(502)
                                .json(
                                        Map.of(
                                                "error",
                                                "Failed to fetch predictions",
                                                "details",
                                                e.getMessage()));
                    } catch (InterruptedException e) {
                        Thread.currentThread().interrupt();
                        ctx.status(502)
                                .json(
                                        Map.of(
                                                "error",
                                                "Request interrupted",
                                                "details",
                                                "MBTA request was interrupted"));
                    }
                });

        app.start(8080);
    }
}
