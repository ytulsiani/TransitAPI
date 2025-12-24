package com.mbta.mbtaapi;

import java.util.ArrayList;
import java.util.List;

public class DirectionSummary {
    public String id;
    public String destination;

    public DirectionSummary() {}

    public DirectionSummary(String id, String destination) {
        this.id = id;
        this.destination = destination;
    }

    public static List<DirectionSummary> fromDestinations(List<String> destinations) {
        List<DirectionSummary> summaries = new ArrayList<>();
        for (int i = 0; i < destinations.size(); i++) {
            summaries.add(new DirectionSummary(String.valueOf(i), destinations.get(i)));
        }
        return summaries;
    }
}
