package com.mbta.mbtaapi;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

@JsonIgnoreProperties(ignoreUnknown = true)
public class RouteResponse {
    public RouteData data;

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class RouteData {
        public RouteAttributes attributes;
    }

    @JsonIgnoreProperties(ignoreUnknown = true)
    public static class RouteAttributes {
        @JsonProperty("direction_destinations")
        public List<String> directionDestinations;
    }
}
