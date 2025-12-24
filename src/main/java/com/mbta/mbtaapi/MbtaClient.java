package com.mbta.mbtaapi;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.rmi.ServerException;
import java.time.Instant;
import java.time.format.DateTimeParseException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.StringJoiner;

public class MbtaClient {
    private final HttpClient httpClient;
    private final ObjectMapper objectMapper;
    private final String baseUrl;

    public MbtaClient(ObjectMapper objectMapper) {
        this("https://api-v3.mbta.com", objectMapper);
    }

    public MbtaClient(String baseUrl, ObjectMapper objectMapper) {
        this.httpClient = HttpClient.newHttpClient();
        this.objectMapper = objectMapper;
        this.baseUrl = baseUrl;
    }

    public List<LineSummary> fetchLines() throws IOException, InterruptedException {
        HttpRequest request =
                HttpRequest.newBuilder()
                        .uri(URI.create(baseUrl + "/lines?include=routes"))
                        .GET()
                        .build();

        HttpResponse<String> response =
                httpClient.send(request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new IOException(
                    "MBTA lines request failed with status " + response.statusCode());
        }

        LineResponse lineResponse = objectMapper.readValue(response.body(), LineResponse.class);

        if (lineResponse == null || lineResponse.data == null) {
            return List.of();
        }

        return lineResponse.data.stream().map(LineSummary::fromLineData).toList();
    }

    public List<StopSummary> fetchStops(String routeId) throws IOException, InterruptedException {
        String encodedRoute = URLEncoder.encode(routeId, StandardCharsets.UTF_8);
        HttpRequest request =
                HttpRequest.newBuilder()
                        .uri(URI.create(baseUrl + "/stops?filter[route]=" + encodedRoute))
                        .GET()
                        .build();

        HttpResponse<String> response =
                httpClient.send(request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new IOException(
                    "MBTA stops request failed with status " + response.statusCode());
        }

        StopResponse stopResponse = objectMapper.readValue(response.body(), StopResponse.class);

        if (stopResponse == null || stopResponse.data == null) {
            return List.of();
        }

        return stopResponse.data.stream().map(StopSummary::fromStopData).toList();
    }

    public List<DirectionSummary> fetchDirections(String routeId)
            throws IOException, InterruptedException {
        String encodedRoute = URLEncoder.encode(routeId, StandardCharsets.UTF_8);
        HttpRequest request =
                HttpRequest.newBuilder()
                        .uri(URI.create(baseUrl + "/routes/" + encodedRoute))
                        .GET()
                        .build();

        HttpResponse<String> response =
                httpClient.send(request, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new IOException(
                    "MBTA directions request failed with status " + response.statusCode());
        }

        RouteResponse routeResponse = objectMapper.readValue(response.body(), RouteResponse.class);

        List<String> destinations =
                routeResponse != null
                        && routeResponse.data != null
                        && routeResponse.data.attributes != null
                        ? routeResponse.data.attributes.directionDestinations
                        : List.of();

        if (destinations == null) {
            return List.of();
        }

        return DirectionSummary.fromDestinations(destinations);
    }

    public List<PredictionSummary> fetchPredictions(PredictionRequest request)
            throws IOException, InterruptedException {
        if (request == null || request.stopId == null || request.stopId.isBlank()) {
            throw new IllegalArgumentException("stopId must not be blank");
        }

        StringBuilder uriBuilder =
                new StringBuilder(baseUrl)
                        .append("/predictions?filter[stop]=")
                        .append(URLEncoder.encode(request.stopId, StandardCharsets.UTF_8));

        if (request.direction != null) {
            uriBuilder
                    .append("&filter[direction_id]=")
                    .append(URLEncoder.encode(String.valueOf(request.direction), StandardCharsets.UTF_8));
        }

        Set<String> routes = request.routes;
        if (routes != null && !routes.isEmpty()) {
            StringJoiner joiner = new StringJoiner(",");
            routes.forEach(joiner::add);
            uriBuilder
                    .append("&filter[route]=")
                    .append(URLEncoder.encode(joiner.toString(), StandardCharsets.UTF_8));
        }

        uriBuilder.append("&sort=arrival_time&include=trip");

        int limit = request.limit != null && request.limit > 0 ? request.limit : 2;
        uriBuilder.append("&page[limit]=").append(limit);

        HttpRequest httpRequest =
                HttpRequest.newBuilder()
                        .uri(URI.create(uriBuilder.toString()))
                        .GET()
                        .build();

        HttpResponse<String> response =
                httpClient.send(httpRequest, HttpResponse.BodyHandlers.ofString());

        if (response.statusCode() != 200) {
            throw new IOException(
                    "MBTA predictions request failed with status " + response.statusCode());
        }

        PredictionResponse predictionResponse =
                objectMapper.readValue(response.body(), PredictionResponse.class);

        if (predictionResponse == null || predictionResponse.data == null || predictionResponse.included == null) {
            throw new ServerException("Issue decoding MBTA response");
        }

        Map<String, String> tripHeadsigns = new HashMap<>();
        for (PredictionResponse.Included inc : predictionResponse.included) {
            if (inc.type.equals("trip")) {
                tripHeadsigns.put(inc.id, inc.attributes.headsign);
            }
        }

        List<PredictionSummary> summaries = new ArrayList<>();
        for (PredictionResponse.PredictionData data : predictionResponse.data) {

            PredictionResponse.PredictionAttributes attr = data.attributes;
            Long arrivalEpoch = parseArrivalEpoch(attr != null ? attr.arrivalTime : null);

            if (arrivalEpoch == null) {
                continue;
            }

            String headsign = attr.headsign != null ? attr.headsign : tripHeadsigns.get(data.tripId());

            summaries.add(
                    new PredictionSummary(
                            headsign,
                            arrivalEpoch,
                            attr.arrivalUncertainty));
        }
        return summaries;
    }

    private Long parseArrivalEpoch(String arrival) throws ServerException {
        if (arrival == null || arrival.isBlank()) {
            return null;
        }
        try {
            return Instant.parse(arrival).getEpochSecond();
        } catch (DateTimeParseException e) {
            throw new ServerException("cannot parse arrival time", e);
        }
    }
}
