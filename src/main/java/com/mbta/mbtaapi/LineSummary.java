package com.mbta.mbtaapi;

import java.util.Collections;
import java.util.List;
import java.util.Objects;
import java.util.Optional;

public class LineSummary {
    public String id;
    public String longName;
    public List<String> routes;

    public LineSummary() {}

    public LineSummary(String id, String longName, List<String> routes) {
        this.id = id;
        this.longName = longName;
        this.routes = routes;
    }

    public static LineSummary fromLineData(LineResponse.LineData lineData) {
        if (lineData == null) {
            return new LineSummary();
        }

        List<String> filteredRoutes =
                Optional.ofNullable(lineData.relationships)
                        .map(relationship -> relationship.routes)
                        .map(routeCollection -> routeCollection.data)
                        .orElse(Collections.emptyList())
                        .stream()
                        .map(route -> route.id)
                        .filter(Objects::nonNull)
                        .filter(routeId -> !routeId.startsWith("Shuttle"))
                        .toList();

        String longName =
                lineData.attributes != null ? lineData.attributes.longName : null;

        return new LineSummary(lineData.id, longName, filteredRoutes);
    }
}
